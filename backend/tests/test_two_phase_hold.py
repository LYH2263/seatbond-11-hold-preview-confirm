"""Two-phase hold flow: precheck issues a token, confirm redeems it exactly once."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import ConflictLog, Hall, HoldToken, SeatHold, Showtime

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    hall = Hall(name="测试厅", rows=5, cols=10, aisle_cols="5,6")
    db.add(hall)
    db.flush()
    db.add(
        Showtime(
            hall_id=hall.id, film_title="测试片", start_at=datetime(2026, 9, 18, 20, 0)
        )
    )
    db.commit()
    db.close()
    yield


def _showtime_id() -> int:
    with TestingSessionLocal() as db:
        return db.scalar(select(Showtime.id))


def _holds() -> list[SeatHold]:
    with TestingSessionLocal() as db:
        return list(db.scalars(select(SeatHold)).all())


def _conflicts() -> list[ConflictLog]:
    with TestingSessionLocal() as db:
        return list(db.scalars(select(ConflictLog)).all())


def _precheck(sid: int, party: int, **extra) -> dict:
    resp = client.post(
        "/api/holds/precheck",
        json={"showtime_id": sid, "party_size": party, **extra},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _confirm(token: str):
    return client.post("/api/holds/confirm", json={"token": token})


def test_precheck_writes_no_hold_and_heat_unchanged():
    sid = _showtime_id()
    before = client.get(f"/api/seatmap/{sid}").json()

    data = _precheck(sid, 3)

    assert data["token"]
    assert data["row"] == 1 and data["start_col"] == 1 and data["end_col"] == 3
    assert datetime.fromisoformat(data["expires_at"]) > datetime.utcnow()
    # 预检不落持座，持座列表没有幽灵单
    assert _holds() == []
    assert client.get("/api/holds").json() == []
    # 座位图热力保持不变
    after = client.get(f"/api/seatmap/{sid}").json()
    assert after == before


def test_confirm_creates_exactly_one_hold():
    sid = _showtime_id()
    pre = _precheck(sid, 3)

    resp = _confirm(pre["token"])

    assert resp.status_code == 200, resp.text
    hold = resp.json()
    assert (hold["row"], hold["start_col"], hold["end_col"]) == (
        pre["row"],
        pre["start_col"],
        pre["end_col"],
    )
    assert hold["party_size"] == 3
    holds = _holds()
    assert len(holds) == 1
    assert holds[0].order_code == hold["order_code"]
    # 令牌已消费
    with TestingSessionLocal() as db:
        tok = db.scalar(select(HoldToken))
        assert tok.consumed_at is not None


def test_duplicate_confirm_rejected():
    sid = _showtime_id()
    pre = _precheck(sid, 2)
    assert _confirm(pre["token"]).status_code == 200

    resp = _confirm(pre["token"])

    assert resp.status_code == 409
    assert len(_holds()) == 1  # 仍只有第一次确认那一条


def test_interfering_occupancy_between_precheck_and_confirm_rejected():
    sid = _showtime_id()
    first = _precheck(sid, 3)
    # 他人对同一批座位完成预检+确认，形成干扰占用
    other = _precheck(sid, 3)
    assert (other["row"], other["start_col"], other["end_col"]) == (
        first["row"],
        first["start_col"],
        first["end_col"],
    )
    assert _confirm(other["token"]).status_code == 200

    resp = _confirm(first["token"])

    assert resp.status_code == 409
    assert "重新预检" in resp.json()["detail"]
    assert len(_holds()) == 1  # 只有他人那一条
    reasons = [c.reason for c in _conflicts()]
    assert any("已被他人占用" in r for r in reasons)


def test_expired_token_rejected():
    sid = _showtime_id()
    pre = _precheck(sid, 2)
    with TestingSessionLocal() as db:
        tok = db.scalar(select(HoldToken))
        tok.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()

    resp = _confirm(pre["token"])

    assert resp.status_code == 409
    assert "过期" in resp.json()["detail"]
    assert _holds() == []
    reasons = [c.reason for c in _conflicts()]
    assert any("过期" in r for r in reasons)


def test_unknown_token_rejected():
    resp = _confirm("no-such-token")
    assert resp.status_code == 404
    assert _holds() == []


def test_precheck_honors_preferred_row():
    sid = _showtime_id()
    pre = _precheck(sid, 2, preferred_row=3)
    assert pre["row"] == 3
    assert (pre["start_col"], pre["end_col"]) == (1, 2)


def test_precheck_without_seats_writes_conflict():
    sid = _showtime_id()
    resp = client.post(
        "/api/holds/precheck", json={"showtime_id": sid, "party_size": 12}
    )
    assert resp.status_code == 409
    assert _holds() == []
    assert db_token_count() == 0
    assert len(_conflicts()) == 1


def db_token_count() -> int:
    with TestingSessionLocal() as db:
        return db.scalar(select(func.count()).select_from(HoldToken))

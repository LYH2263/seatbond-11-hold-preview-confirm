import { useEffect, useState } from "react";
import { api } from "../api/client";

type Show = { id: number; film_title: string; hall_name?: string };
type Precheck = {
  token: string;
  showtime_id: number;
  party_size: number;
  row: number;
  start_col: number;
  end_col: number;
  expires_at: string;
};
type Hold = {
  id: number;
  order_code: string;
  row: number;
  start_col: number;
  end_col: number;
  party_size: number;
};

function remainingSeconds(expiresAt: string): number {
  // 后端以 UTC 朴素时间下发，按 UTC 解析
  const iso = expiresAt.endsWith("Z") ? expiresAt : `${expiresAt}Z`;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 1000));
}

function errText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* 非 JSON 错误体，原样展示 */
  }
  return raw;
}

export default function HoldPage() {
  const [shows, setShows] = useState<Show[]>([]);
  const [sid, setSid] = useState<number | "">("");
  const [party, setParty] = useState(3);
  const [prefRow, setPrefRow] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [pre, setPre] = useState<Precheck | null>(null);
  const [left, setLeft] = useState(0);
  const [last, setLast] = useState<Hold | null>(null);

  useEffect(() => {
    api<Show[]>("/showtimes").then((s) => {
      setShows(s);
      if (s[0]) setSid(s[0].id);
    });
  }, []);

  // 令牌倒计时；归零即失效，需重新预检
  useEffect(() => {
    if (!pre) return;
    const timer = setInterval(() => {
      const remain = remainingSeconds(pre.expires_at);
      setLeft(remain);
      if (remain === 0) {
        setPre(null);
        setMsg("");
        setErr("确认令牌已过期，请重新预检");
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [pre]);

  async function precheck() {
    setMsg("");
    setErr("");
    setLast(null);
    try {
      const body: Record<string, unknown> = { showtime_id: sid, party_size: party };
      if (prefRow) body.preferred_row = Number(prefRow);
      const p = await api<Precheck>("/holds/precheck", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setPre(p);
      setLeft(remainingSeconds(p.expires_at));
    } catch (e) {
      setPre(null);
      setErr(errText(e));
    }
  }

  async function confirm() {
    if (!pre) return;
    setMsg("");
    setErr("");
    try {
      const hold = await api<Hold>("/holds/confirm", {
        method: "POST",
        body: JSON.stringify({ token: pre.token }),
      });
      setPre(null);
      setLast(hold);
      setMsg(`已锁座 ${hold.order_code}：第${hold.row}排 ${hold.start_col}-${hold.end_col}`);
    } catch (e) {
      setPre(null);
      setErr(errText(e));
    }
  }

  return (
    <>
      <h2>锁座</h2>
      <div className="toolbar">
        <select
          value={sid}
          disabled={!!pre}
          onChange={(e) => setSid(Number(e.target.value))}
        >
          {shows.map((s) => (
            <option key={s.id} value={s.id}>
              {s.film_title} · {s.hall_name}
            </option>
          ))}
        </select>
        <label>
          人数{" "}
          <input
            type="number"
            min={1}
            max={12}
            value={party}
            disabled={!!pre}
            onChange={(e) => setParty(Number(e.target.value))}
            style={{ width: 72 }}
          />
        </label>
        <label>
          优先排{" "}
          <input
            value={prefRow}
            disabled={!!pre}
            onChange={(e) => setPrefRow(e.target.value)}
            placeholder="可选"
            style={{ width: 72 }}
          />
        </label>
        {!pre && <button onClick={precheck}>预检连座</button>}
      </div>
      {pre && (
        <div className="toolbar">
          <span className="mono">
            预检结果：第{pre.row}排 {pre.start_col}-{pre.end_col}列 · {pre.party_size}人 ·
            剩余 {left}s
          </span>
          <button onClick={confirm}>确认锁座</button>
          <button
            onClick={() => {
              setPre(null);
              setMsg("");
              setErr("");
            }}
          >
            取消
          </button>
        </div>
      )}
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}
      {last && (
        <p className="mono">
          订单 {last.order_code} · {last.party_size} 人 · R{last.row} C{last.start_col}-
          {last.end_col}
        </p>
      )}
    </>
  );
}

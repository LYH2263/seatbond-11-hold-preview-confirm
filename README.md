# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座。锁座为两阶段：先预检领取短时确认令牌，再凭令牌确认落库。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |
| API 文档 | http://localhost:9100/docs |
| Postgres | localhost:5442 |

健康检查：`GET http://localhost:9100/api/health`

## 页面

- `/halls` — 影厅
- `/showtimes` — 场次
- `/seatmap` — 座位图（大网格热力）
- `/hold` — 锁座
- `/orders` — 订单
- `/conflicts` — 冲突

## 使用说明

1. 在影厅与场次页确认厅图与排期。
2. 打开座位图查看占用热力，在锁座页输入连座人数并预检，页面展示将占用的排与起止列。
3. 在令牌有效期内确认，持座落库；令牌过期或座位被他人占用需重新预检。
4. 订单页查看持座结果；冲突页查看重叠与失效请求。

## 接口

- `POST /api/holds/precheck` — 预检：返回确认令牌与预检坐标，不写持座。
- `POST /api/holds/confirm` — 确认：携带令牌落库；同一令牌仅可成功确认一次。

令牌有效期由 `HOLD_TOKEN_TTL_SECONDS` 控制（默认 120 秒）。

## 开发与测试

```bash
docker compose exec api pytest -q
```

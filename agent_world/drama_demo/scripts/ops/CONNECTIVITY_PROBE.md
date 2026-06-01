# 连通性探针 · 接口描述（单端点 / Single-API）

供"正式网站后端"联调用的本机 HTTP 服务。脚本：[`connectivity_probe.py`](connectivity_probe.py)。

对方只要**一个 API**——前后端所有数据交流都走同一个 URL。本探针即按此约定实现：
唯一业务端点 **`POST /api`**，请求体用 `action` 字段指定要哪类数据，统一信封返回
HTTP 200 + 样例 JSON。返回的是**形状贴近 demo 的固定假数据**（可安全对外），
仅用于连通性 / 接口契约验证，不读真实 demo 数据库。

## 1. 启动 / 停止

```bash
cd agent_world/drama_demo/scripts/ops
python3 connectivity_probe.py                 # 0.0.0.0:8088，无鉴权
python3 connectivity_probe.py --port 9000      # 自定义端口
python3 connectivity_probe.py --token SECRET   # 要求请求带 X-Probe-Token: SECRET
# 停止：前台 Ctrl+C；后台进程 pkill -f connectivity_probe.py
```

启动时控制台打印本机所有可达 IPv4，把局域网网段（如 `192.168.x.x`）的
`http://IP:端口/api` 交给对方后端。

## 2. 接入信息

| 项 | 值 |
|----|----|
| 协议 | HTTP/1.1 |
| **唯一端点** | **`POST /api`**（前后端所有数据交流均经此） |
| 绑定 | `0.0.0.0`，默认端口 `8088` |
| 请求/响应类型 | `application/json; charset=utf-8`（UTF-8，中文不转义） |
| CORS | `Access-Control-Allow-Origin: *`，支持 `OPTIONS` 预检 |
| 鉴权 | 默认无；带 `--token` 时需头 `X-Probe-Token: <token>`，否则 401 |
| 自描述 | `GET /api`（不带 action）返回 action 目录，便于发现接口 |

> **外网可达**：本机在内网，外部后端访问需 ①路由器端口转发，或 ②隧道
> （`ngrok http 8088` / `cloudflared`），把得到的公网 URL 交给对方。

## 3. 请求格式

唯一端点 `POST /api`，请求体：

```json
{ "action": "demo.summary", "params": { /* 可选，按 action 而定 */ } }
```

- `action`（string，必填）：要执行的动作 / 要取的数据，见 §5。
- `params`（object，可选）：该动作的参数。

> 兼容：`GET /api?action=demo.summary` 也可（便于浏览器/curl 快速探测）；
> 但正式调用以 `POST /api` + JSON 体为准。

## 4. 响应格式（统一信封）

恒返回 **HTTP 200**（鉴权失败除外，返回 401）。成功与否看体内 `success`：

```json
{
  "success": true,
  "action": "demo.summary",
  "data": { /* 该 action 的业务数据，见 §5 */ },
  "meta": {
    "service": "hbm-demo-connectivity-probe",
    "version": "2.0",
    "endpoint": "POST /api",
    "request_id": "req-000002",
    "server_time": "2026-05-29T12:26:27Z",
    "note": "样例数据，仅用于连通性 / 接口契约验证"
  }
}
```

错误（仍为 HTTP 200，`success:false`）：

| 场景 | `data.error` |
|------|-------------|
| 未知 action | `unknown_action`（附 `available_actions`） |
| 请求体非合法 JSON | `invalid_json` |

鉴权失败（**HTTP 401**，仅 `--token` 启动时）：

```json
{ "success": false, "action": null, "error": "unauthorized",
  "message": "缺少或错误的 X-Probe-Token", "meta": { "request_id": "..." } }
```

## 5. action 清单

| action | 说明 | `params` | `data` 形状 |
|--------|------|----------|-------------|
| `ping` | 存活探针 | — | `{ "status": "ok" }` |
| `demo.summary` | demo 总览 | — | §5.1 |
| `demo.agents` | Agent 列表 | — | §5.2 |
| `demo.world` | 世界快照（房间/占位/近期事件） | — | §5.3 |
| `demo.session` | 当前 session 状态 | — | §5.4 |
| **`demo.all`** | **一次取回上面全部数据** | — | §5.5 |
| **`batch`** | **一次发起多个 action** | `{ "calls": [ {action, params}, ... ] }` | §5.6 |
| `echo` | 回显 `params`，验证链路 | 任意 | `{ "echo": <params> }` |

### 5.1 `demo.summary`

```json
{ "sim_id": "hbm_memory_war", "title": "HBM 内存争夺战",
  "phase": 3, "phase_label": "Phase 3 · 董事会博弈",
  "tick": 1287, "status": "running", "agent_count": 8,
  "started_at": "2026-05-29T08:00:00Z" }
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `sim_id` | string | 模拟实例 id |
| `phase` | int (1–4) | 当前剧情幕 |
| `phase_label` | string | 幕的可读标题 |
| `tick` | int | 世界循环计数（约 1/秒） |
| `status` | string | `running`/`paused`/`completed`/`game_over` |
| `agent_count` | int | Agent 总数（含玩家 0） |

### 5.2 `demo.agents`

```json
{ "agents": [ { "agent_id": 0, "name": "玩家", "role": "player", "place": "boardroom" } ],
  "count": 8 }
```

`agent_id`：0=玩家，1–7=NPC；`role` 角色标签；`place` 所在房间 key。

### 5.3 `demo.world`

```json
{ "tick": 1287,
  "rooms": [ { "place": "boardroom", "label": "董事会议室", "occupants": [0,2,3] } ],
  "recent_events": [
    { "tick": 1285, "type": "speak", "agent_id": 2, "place": "boardroom", "text": "…" },
    { "tick": 1286, "type": "move", "agent_id": 7, "from": "office_b", "to": "lobby" } ] }
```

`rooms[].occupants` 为房间内 agent_id；事件 `type` 为 `speak`（带 `text`）或 `move`（带 `from`/`to`）。

### 5.4 `demo.session`

```json
{ "sim_id": "hbm_memory_war", "turn": 14, "phase": 3, "player_score": 72,
  "loop": { "running": true, "paused": false, "tick": 1287 }, "ending": null }
```

`turn` 玩家回合数；`player_score` 分数；`loop` 世界循环状态；`ending` 结束时为结局对象否则 null。

### 5.5 `demo.all`

把 §5.1–5.4 打包返回，便于前端一次拉全：

```json
{ "summary": { … }, "agents": { … }, "world": { … }, "session": { … } }
```

### 5.6 `batch`

一次请求执行多个 action，结果按序返回：

```json
// 请求
{ "action": "batch", "params": { "calls": [
    { "action": "demo.summary" },
    { "action": "demo.world" },
    { "action": "echo", "params": { "hi": 1 } } ] } }

// 响应 data
{ "count": 3, "results": [
    { "index": 0, "action": "demo.summary", "success": true, "data": { … } },
    { "index": 1, "action": "demo.world",   "success": true, "data": { … } },
    { "index": 2, "action": "echo",         "success": true, "data": { "echo": { "hi": 1 } } } ] }
```

## 6. 联调自测命令

```bash
# 自描述目录（发现所有 action）
curl -s http://<IP>:8088/api

# 单个 action
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"action":"demo.summary"}' http://<IP>:8088/api

# 一次全取
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"action":"demo.all"}' http://<IP>:8088/api

# 一次多调
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"action":"batch","params":{"calls":[{"action":"ping"},{"action":"demo.world"}]}}' \
  http://<IP>:8088/api

# 带鉴权（探针以 --token SECRET 启动时）
curl -s -X POST -H 'Content-Type: application/json' -H 'X-Probe-Token: SECRET' \
  -d '{"action":"demo.session"}' http://<IP>:8088/api
```

服务端控制台逐条打印进来的请求（方法/路径/来源 IP/关键头/请求体预览）+ 同号
`request_id`，可与对方后端日志对账。

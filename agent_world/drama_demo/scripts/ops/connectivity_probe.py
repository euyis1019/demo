#!/usr/bin/env python3
"""连通性测试探针 (connectivity probe) —— 单端点(single-API)版。

用途
----
对方"正式网站后端"只要**一个 API**：前后端所有数据交流都走同一个 URL。
本探针即按此约定实现：单一入口 `POST /api`，请求体用 `action` 字段指定要哪类
数据，统一信封返回 HTTP 200 + 样例 JSON。它不读真实 demo 数据库，返回的是
形状贴近 demo 的**固定假数据**，仅用于连通性 / 接口契约验证。

运行
----
    python3 connectivity_probe.py                 # 0.0.0.0:8088
    python3 connectivity_probe.py --port 9000
    python3 connectivity_probe.py --token SECRET   # 要求 X-Probe-Token 头匹配

协议要点
--------
- 唯一业务端点：`POST /api`，体 `{"action": "<名>", "params": {...}}`。
- 一次取全部：`action="demo.all"`；一次多调：`action="batch"`。
- GET /api 不带 action -> 返回"动作目录"(自描述)，方便对方发现接口。
- 统一信封：{"success", "action", "data", "meta"}；鉴权失败 401，其余恒 200。
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# --- 样例数据：形状贴近 demo，但全部为固定假数据，可安全对外 ----------------

SAMPLE_SUMMARY = {
    "sim_id": "canglan_sword",
    "title": "HBM 内存争夺战",
    "phase": 3,
    "phase_label": "Phase 3 · 董事会博弈",
    "tick": 1287,
    "status": "running",
    "agent_count": 8,
    "started_at": "2026-05-29T08:00:00Z",
}

SAMPLE_AGENTS = [
    {"agent_id": 0, "name": "玩家", "role": "player", "place": "boardroom"},
    {"agent_id": 1, "name": "接待前台", "role": "reception", "place": "lobby"},
    {"agent_id": 2, "name": "Jensen Hwang", "role": "nvidia_ceo", "place": "boardroom"},
    {"agent_id": 3, "name": "Tech VP", "role": "tech_vp", "place": "boardroom"},
    {"agent_id": 4, "name": "SK Hynix CEO", "role": "hbm_supplier", "place": "office_a"},
    {"agent_id": 5, "name": "Micron CEO", "role": "hbm_supplier", "place": "office_b"},
    {"agent_id": 6, "name": "Samsung CEO", "role": "hbm_supplier", "place": "office_a"},
    {"agent_id": 7, "name": "Sam Altman", "role": "openai_ceo", "place": "lobby"},
]

SAMPLE_WORLD = {
    "tick": 1287,
    "rooms": [
        {"place": "lobby", "label": "前台大厅", "occupants": [1, 7]},
        {"place": "boardroom", "label": "董事会议室", "occupants": [0, 2, 3]},
        {"place": "office_a", "label": "办公室 A", "occupants": [4, 6]},
        {"place": "office_b", "label": "办公室 B", "occupants": [5]},
    ],
    "recent_events": [
        {"tick": 1285, "type": "speak", "agent_id": 2, "place": "boardroom",
         "text": "我们需要在 Q3 锁定 HBM3E 的产能。"},
        {"tick": 1286, "type": "move", "agent_id": 7, "from": "office_b", "to": "lobby"},
    ],
}

SAMPLE_SESSION = {
    "sim_id": "canglan_sword",
    "turn": 14,
    "phase": 3,
    "player_score": 72,
    "loop": {"running": True, "paused": False, "tick": 1287},
    "ending": None,
}


# --- 动作分发：所有数据交流都通过这些 action ---------------------------------

def _act_ping(params):    return {"status": "ok"}
def _act_summary(params): return SAMPLE_SUMMARY
def _act_agents(params):  return {"agents": SAMPLE_AGENTS, "count": len(SAMPLE_AGENTS)}
def _act_world(params):   return SAMPLE_WORLD
def _act_session(params): return SAMPLE_SESSION


def _act_all(params):
    """一次取回前后端可能需要的全部数据。"""
    return {
        "summary": SAMPLE_SUMMARY,
        "agents": {"agents": SAMPLE_AGENTS, "count": len(SAMPLE_AGENTS)},
        "world": SAMPLE_WORLD,
        "session": SAMPLE_SESSION,
    }


def _act_echo(params):
    """回显 params，验证请求体链路与编码。"""
    return {"echo": params}


# batch 在 dispatch 内特殊处理（需要复用分发器），这里仅占位声明可用
ACTIONS = {
    "ping": _act_ping,
    "demo.summary": _act_summary,
    "demo.agents": _act_agents,
    "demo.world": _act_world,
    "demo.session": _act_session,
    "demo.all": _act_all,
    "echo": _act_echo,
}
ACTION_NAMES = sorted(list(ACTIONS) + ["batch"])


def dispatch(action: str, params: dict):
    """返回 (success, data_or_error)。batch 递归调用自身。"""
    if action == "batch":
        calls = (params or {}).get("calls", [])
        results = []
        for i, call in enumerate(calls):
            sub_action = (call or {}).get("action", "")
            sub_params = (call or {}).get("params", {}) or {}
            ok, data = dispatch(sub_action, sub_params)
            results.append({"index": i, "action": sub_action,
                            "success": ok, "data": data})
        return True, {"results": results, "count": len(results)}

    handler = ACTIONS.get(action)
    if handler is None:
        return False, {"error": "unknown_action", "action": action,
                       "available_actions": ACTION_NAMES}
    return True, handler(params or {})


def _envelope(action: str, ok: bool, data, request_id: str):
    return {
        "success": ok,
        "action": action,
        "data": data,
        "meta": {
            "service": "hbm-demo-connectivity-probe",
            "version": "2.0",
            "endpoint": "POST /api",
            "request_id": request_id,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "note": "样例数据，仅用于连通性 / 接口契约验证",
        },
    }


class ProbeHandler(BaseHTTPRequestHandler):
    server_version = "DramaDemoProbe/2.0"
    auth_token: str | None = None  # 由 server 注入
    _seq = 0

    # --- 工具 --------------------------------------------------------------
    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def _next_request_id(self) -> str:
        type(self)._seq += 1
        return f"req-{type(self)._seq:06d}"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Probe-Token")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _log_request_detail(self, request_id: str, body: bytes) -> None:
        parsed = urlparse(self.path)
        ts = datetime.now(timezone.utc).isoformat()
        print(f"\n=== [{ts}] {request_id} ===")
        print(f"  {self.command} {self.path}  <- {self._client_ip()}")
        if parsed.query:
            print(f"  query: {parse_qs(parsed.query)}")
        for h in ("User-Agent", "Content-Type", "X-Probe-Token", "X-Forwarded-For"):
            if self.headers.get(h):
                print(f"  {h}: {self.headers.get(h)}")
        if body:
            print(f"  body ({len(body)}B): {body[:1000].decode('utf-8', 'replace')}")
        sys.stdout.flush()

    def _catalog(self, request_id: str) -> dict:
        """自描述：列出唯一端点与全部 action。"""
        return _envelope("__catalog__", True, {
            "endpoint": "POST /api",
            "request_schema": {"action": "<string>", "params": "<object, 可选>"},
            "actions": ACTION_NAMES,
            "examples": {
                "single": {"action": "demo.summary"},
                "all_in_one": {"action": "demo.all"},
                "batch": {"action": "batch", "params": {"calls": [
                    {"action": "demo.summary"}, {"action": "demo.world"}]}},
            },
        }, request_id)

    # --- 主流程 ------------------------------------------------------------
    def _handle(self) -> None:
        request_id = self._next_request_id()
        body = self._read_body()
        self._log_request_detail(request_id, body)

        # 可选鉴权
        if self.auth_token is not None and self.headers.get("X-Probe-Token") != self.auth_token:
            self._send_json(401, {"success": False, "action": None,
                                  "error": "unauthorized",
                                  "message": "缺少或错误的 X-Probe-Token",
                                  "meta": {"request_id": request_id}})
            return

        path = urlparse(self.path).path.rstrip("/") or "/"

        # 解析 action：POST 优先读 JSON 体，GET/兜底读 ?action= 查询参数
        action, params = None, {}
        if body:
            try:
                parsed_body = json.loads(body.decode("utf-8"))
                if isinstance(parsed_body, dict):
                    action = parsed_body.get("action")
                    params = parsed_body.get("params") or {}
            except json.JSONDecodeError:
                self._send_json(200, _envelope(None, False,
                    {"error": "invalid_json", "message": "请求体不是合法 JSON"}, request_id))
                return
        if action is None:
            qs = parse_qs(urlparse(self.path).query)
            if "action" in qs:
                action = qs["action"][0]

        # 无 action -> 返回自描述目录（含 / 与 /api 的 GET 探测）
        if not action:
            self._send_json(200, self._catalog(request_id))
            return

        ok, data = dispatch(action, params)
        self._send_json(200, _envelope(action, ok, data, request_id))

    def do_GET(self):    self._handle()
    def do_POST(self):   self._handle()
    def do_HEAD(self):   self._handle()

    def do_OPTIONS(self):  # CORS 预检
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):  # 静音默认 access log
        pass


def _local_ipv4s() -> list[str]:
    ips: set[str] = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    ips.discard("127.0.0.1")
    return sorted(ips)


def main() -> int:
    ap = argparse.ArgumentParser(description="drama demo 连通性探针（单端点版）")
    ap.add_argument("--host", default="0.0.0.0", help="绑定地址（默认 0.0.0.0，对外可达）")
    ap.add_argument("--port", type=int, default=8088, help="端口（默认 8088）")
    ap.add_argument("--token", default=None, help="可选：要求请求带 X-Probe-Token 此值")
    args = ap.parse_args()

    ProbeHandler.auth_token = args.token
    httpd = ThreadingHTTPServer((args.host, args.port), ProbeHandler)

    print("=" * 64)
    print("drama demo 连通性探针（单端点版）已启动")
    print(f"  绑定:     {args.host}:{args.port}")
    print(f"  唯一端点: POST http://<IP>:{args.port}/api   体: {{\"action\": \"...\"}}")
    print(f"  鉴权:     {'需要 X-Probe-Token=' + args.token if args.token else '无（任意请求均回 200）'}")
    print(f"  自描述:   GET http://127.0.0.1:{args.port}/api  （返回 action 目录）")
    lan = _local_ipv4s()
    if lan:
        print("  局域网可达地址（交给对方后端）:")
        for ip in lan:
            print(f"    http://{ip}:{args.port}/api")
    else:
        print("  （未探测到非回环 IPv4，请用 `ifconfig` 自查）")
    print("  外网访问需在路由器做端口转发，或用隧道（ngrok/cloudflared 等）")
    print("  Ctrl+C 停止")
    print("=" * 64)
    sys.stdout.flush()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n探针已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

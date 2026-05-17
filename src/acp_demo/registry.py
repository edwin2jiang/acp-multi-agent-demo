#!/usr/bin/env python3
"""
ACP Registry - 完整的注册中心实现

功能：
1. Agent 注册 / 注销（带完整 Manifest）
2. 心跳机制（Agent 定期上报存活）
3. 自动清理（超时未心跳的 Agent 自动移除）
4. 能力搜索（Client 按能力筛选 Agent）
5. 健康检查（Registry 自身状态）
"""

import json
import time
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ============================================================
#  数据结构
# ============================================================

# 已注册的 Agent
agents = {}
agents_lock = threading.Lock()

# 心跳超时（秒）：超过这个时间没心跳，认为 Agent 已死
HEARTBEAT_TIMEOUT = 30

# 清理间隔（秒）
CLEANUP_INTERVAL = 10


# ============================================================
#  Agent Manifest 结构
# ============================================================
#
# {
#   "id": "agent-xxx",              # 唯一 ID
#   "name": "ACP Worker 1",         # 显示名
#   "description": "同能力 worker", # 描述
#   "version": "1.0.0",             # 版本
#   "capabilities": ["python"],     # 能力标签
#   "input_content_types": ["text/plain", "application/json"],
#   "output_content_types": ["text/plain"],
#   "skills": [{"name": "playwright", ...}],
#   "transport": "stdio",           # 传输方式：stdio / http
#   "endpoint": null,               # 远程地址（http 模式）
#   "registered_at": 1715700000.0,  # 注册时间
#   "last_heartbeat": 1715700000.0, # 最后心跳时间
#   "status": "active"              # 状态：active / busy / offline
# }


def log(msg):
    print(f"[Registry] {msg}")


# ============================================================
#  自动清理线程
# ============================================================

def cleanup_stale_agents():
    """定期清理超时未心跳的 Agent"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        now = time.time()
        stale = []
        with agents_lock:
            for agent_id, agent in agents.items():
                if now - agent["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                    stale.append(agent_id)
            for agent_id in stale:
                name = agents[agent_id]["name"]
                del agents[agent_id]
                log(f"自动清理: {name} ({agent_id}) - 心跳超时")


# ============================================================
#  HTTP Handler
# ============================================================

class RegistryHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass  # 禁用默认日志

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc}") from exc

    # ----------------------------------------------------------
    #  GET 请求
    # ----------------------------------------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # GET /agents — 列出所有 Agent（支持按能力筛选）
        if path == "/agents":
            capability_filter = params.get("capability", [None])[0]
            status_filter = params.get("status", [None])[0]

            with agents_lock:
                result = list(agents.values())

            # 按能力筛选
            if capability_filter:
                result = [a for a in result if capability_filter in a.get("capabilities", [])]

            # 按状态筛选
            if status_filter:
                result = [a for a in result if a.get("status") == status_filter]

            self._send_json(200, {"agents": result, "count": len(result)})

        # GET /agents/{id} — 查询单个 Agent
        elif path.startswith("/agents/"):
            agent_id = path.split("/")[-1]
            with agents_lock:
                agent = agents.get(agent_id)
            if agent:
                self._send_json(200, agent)
            else:
                self._send_json(404, {"error": "Agent not found"})

        # GET /health — Registry 健康检查
        elif path == "/health":
            with agents_lock:
                total = len(agents)
                active = sum(1 for a in agents.values() if a["status"] == "active")
                busy = sum(1 for a in agents.values() if a["status"] == "busy")
            self._send_json(200, {
                "status": "healthy",
                "agents_total": total,
                "agents_active": active,
                "agents_busy": busy,
                "heartbeat_timeout": HEARTBEAT_TIMEOUT,
                "uptime": time.time()
            })

        # GET /capabilities — 列出所有已注册的能力
        elif path == "/capabilities":
            caps = set()
            with agents_lock:
                for a in agents.values():
                    caps.update(a.get("capabilities", []))
            self._send_json(200, {"capabilities": sorted(caps)})

        # GET /skills — 列出所有已注册的 Skill
        elif path == "/skills":
            skill_filter = params.get("name", [None])[0]
            skills = {}
            with agents_lock:
                for agent in agents.values():
                    for skill in agent.get("skills", []):
                        name = skill.get("name")
                        if not name:
                            continue
                        if skill_filter and skill_filter != name:
                            continue
                        entry = skills.setdefault(name, {**skill, "agents": []})
                        entry["agents"].append({
                            "id": agent["id"],
                            "name": agent["name"],
                            "status": agent["status"],
                        })
            self._send_json(200, {"skills": list(skills.values()), "count": len(skills)})

        else:
            self._send_json(404, {"error": "Not found"})

    # ----------------------------------------------------------
    #  POST 请求
    # ----------------------------------------------------------

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            data = self._read_body()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        # POST /register — Agent 注册
        if path == "/register":
            agent_id = data.get("id") or f"agent-{uuid.uuid4().hex[:8]}"

            agent = {
                "id": agent_id,
                "name": data.get("name", "Unknown"),
                "description": data.get("description", ""),
                "version": data.get("version", "0.0.0"),
                "capabilities": data.get("capabilities", []),
                "skills": data.get("skills", []),
                "input_content_types": data.get("input_content_types", ["text/plain"]),
                "output_content_types": data.get("output_content_types", ["text/plain"]),
                "transport": data.get("transport", "stdio"),
                "endpoint": data.get("endpoint"),
                "metadata": data.get("metadata", {}),
                "registered_at": time.time(),
                "last_heartbeat": time.time(),
                "status": "active"
            }

            with agents_lock:
                agents[agent_id] = agent

            log(f"注册: {agent['name']} ({agent_id}) - {agent['capabilities']}")
            self._send_json(200, {"status": "registered", "id": agent_id})

        # POST /heartbeat — Agent 心跳
        elif path == "/heartbeat":
            agent_id = data.get("id")
            status = data.get("status", "active")

            with agents_lock:
                agent = agents.get(agent_id)
                if agent:
                    agent["last_heartbeat"] = time.time()
                    agent["status"] = status
                    self._send_json(200, {"status": "ok"})
                else:
                    self._send_json(404, {"error": "Agent not registered"})

        # POST /unregister — Agent 注销
        elif path == "/unregister":
            agent_id = data.get("id")

            with agents_lock:
                removed = agents.pop(agent_id, None)

            if removed:
                log(f"注销: {removed['name']} ({agent_id})")
                self._send_json(200, {"status": "unregistered"})
            else:
                self._send_json(404, {"error": "Agent not found"})

        # POST /search — 按能力搜索 Agent
        elif path == "/search":
            required_caps = data.get("capabilities", [])
            required_skills = data.get("skills", [])
            content_type = data.get("input_content_type")

            with agents_lock:
                result = []
                for a in agents.values():
                    if a["status"] != "active":
                        continue
                    # 检查是否具备所有要求的能力
                    if required_caps and not all(c in a["capabilities"] for c in required_caps):
                        continue
                    skill_names = [s.get("name") for s in a.get("skills", [])]
                    if required_skills and not all(s in skill_names for s in required_skills):
                        continue
                    # 检查是否支持指定的输入类型
                    if content_type and content_type not in a["input_content_types"]:
                        continue
                    result.append(a)

            self._send_json(200, {"agents": result, "count": len(result)})

        else:
            self._send_json(404, {"error": "Not found"})


# ============================================================
#  启动
# ============================================================

def run_registry(port=3000):
    # 启动清理线程
    cleaner = threading.Thread(target=cleanup_stale_agents, daemon=True)
    cleaner.start()

    server = HTTPServer(("127.0.0.1", port), RegistryHandler)

    log(f"启动注册中心: http://127.0.0.1:{port}")
    log(f"心跳超时: {HEARTBEAT_TIMEOUT}s, 清理间隔: {CLEANUP_INTERVAL}s")
    log("")
    log("API 端点:")
    log(f"  GET  /agents              - 列出所有 Agent")
    log(f"  GET  /agents?capability=x - 按能力筛选")
    log(f"  GET  /agents/{{id}}        - 查询单个 Agent")
    log(f"  GET  /capabilities        - 列出所有能力")
    log(f"  GET  /skills              - 列出所有 Skill")
    log(f"  GET  /health              - Registry 健康检查")
    log(f"  POST /register            - Agent 注册")
    log(f"  POST /heartbeat           - Agent 心跳")
    log(f"  POST /unregister          - Agent 注销")
    log(f"  POST /search              - 按能力搜索")

    server.serve_forever()


if __name__ == "__main__":
    run_registry()

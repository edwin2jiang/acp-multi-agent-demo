#!/usr/bin/env python3
"""
ACP Registry - 注册中心
Agent 启动时注册自己，Client 查询可用 Agent
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


# 存储已注册的 Agent
agents = {}
lock = threading.Lock()


class RegistryHandler(BaseHTTPRequestHandler):
    """HTTP API 处理请求"""
    
    def log_message(self, format, *args):
        """禁用默认日志，用自定义格式"""
        pass
    
    def do_GET(self):
        if self.path == "/agents":
            # 列出所有已注册的 Agent
            with lock:
                agent_list = [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "description": a["description"],
                        "capabilities": a["capabilities"],
                        "registered_at": a["registered_at"]
                    }
                    for a in agents.values()
                ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"agents": agent_list}, indent=2).encode())
        
        elif self.path.startswith("/agents/"):
            # 查询单个 Agent
            agent_id = self.path.split("/")[-1]
            with lock:
                agent = agents.get(agent_id)
            if agent:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(agent, indent=2).encode())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error": "Agent not found"}')
        
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        if self.path == "/register":
            # Agent 注册自己
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            
            agent_id = data.get("id")
            with lock:
                agents[agent_id] = {
                    "id": agent_id,
                    "name": data.get("name"),
                    "description": data.get("description"),
                    "capabilities": data.get("capabilities", []),
                    "registered_at": time.time()
                }
            
            print(f"[Registry] Agent 注册: {data.get('name')} ({agent_id})")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "registered"}).encode())
        
        elif self.path == "/unregister":
            # Agent 注销
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            
            agent_id = data.get("id")
            with lock:
                removed = agents.pop(agent_id, None)
            
            if removed:
                print(f"[Registry] Agent 注销: {agent_id}")
                self.send_response(200)
                self.wfile.write(json.dumps({"status": "unregistered"}).encode())
            else:
                self.send_response(404)
                self.wfile.write(json.dumps({"error": "Agent not found"}).encode())
        
        else:
            self.send_response(404)
            self.end_headers()


def run_registry(port=3000):
    server = HTTPServer(("127.0.0.1", port), RegistryHandler)
    print(f"[Registry] 启动注册中心: http://127.0.0.1:{port}")
    print(f"[Registry] 查询 Agent: GET /agents")
    print(f"[Registry] 注册 Agent: POST /register")
    server.serve_forever()


if __name__ == "__main__":
    run_registry()

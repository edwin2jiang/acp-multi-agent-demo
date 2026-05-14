#!/usr/bin/env python3
"""
Agent A - Python 代码专家
支持：注册、心跳、完整 Manifest
"""

import json
import sys
import time
import threading
import requests

AGENT_ID = "python-agent"
AGENT_NAME = "Python Agent"
AGENT_DESC = "擅长 Python 代码编写、调试和重构"
AGENT_VERSION = "1.0.0"
REGISTRY_URL = "http://127.0.0.1:3000"

sessions = {}
session_counter = 0
current_status = "active"


def log(msg):
    print(f"[{AGENT_NAME}] {msg}", file=sys.stderr)


# ============================================================
#  Registry 交互
# ============================================================

def register():
    """注册到 Registry（带完整 Manifest）"""
    try:
        resp = requests.post(f"{REGISTRY_URL}/register", json={
            "id": AGENT_ID,
            "name": AGENT_NAME,
            "description": AGENT_DESC,
            "version": AGENT_VERSION,
            "capabilities": ["python", "debugging", "refactoring", "testing"],
            "input_content_types": ["text/plain", "application/json"],
            "output_content_types": ["text/plain", "application/json"],
            "transport": "stdio",
            "endpoint": None
        })
        if resp.status_code == 200:
            log(f"注册成功 (v{AGENT_VERSION})")
        else:
            log(f"注册失败: {resp.text}")
    except Exception as e:
        log(f"注册失败: {e}")


def unregister():
    """从 Registry 注销"""
    try:
        requests.post(f"{REGISTRY_URL}/unregister", json={"id": AGENT_ID})
        log("已注销")
    except:
        pass


def heartbeat_loop():
    """心跳线程：定期向 Registry 报告存活"""
    while True:
        try:
            requests.post(f"{REGISTRY_URL}/heartbeat", json={
                "id": AGENT_ID,
                "status": current_status
            }, timeout=3)
        except:
            pass
        time.sleep(10)  # 每 10 秒心跳一次


# ============================================================
#  ACP 协议处理
# ============================================================

def handle_request(req):
    global session_counter, current_status
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "loadSession": True,
                    "sessionCapabilities": {"resume": {}, "close": {}}
                },
                "agentInfo": {
                    "name": AGENT_NAME,
                    "version": AGENT_VERSION,
                    "description": AGENT_DESC
                }
            }
        }

    elif method == "session/new":
        session_counter += 1
        session_id = f"py_{session_counter:03d}"
        sessions[session_id] = {"cwd": params.get("cwd", "/tmp"), "created_at": time.time()}
        log(f"新会话: {session_id}")
        return {"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": session_id}}

    elif method == "session/prompt":
        session_id = params.get("sessionId")
        prompt = params.get("prompt", [])
        text = ""
        for p in prompt:
            if isinstance(p, dict) and p.get("type") == "text":
                text = p.get("text", "")
                break

        log(f"处理: {text[:40]}")
        current_status = "busy"  # 标记为忙碌

        # 模拟 LLM 处理
        time.sleep(0.5)

        response = f"[{AGENT_NAME}] 处理完成: '{text}'"

        update = {
            "jsonrpc": "2.0", "method": "session/update",
            "params": {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": response}
                }
            }
        }
        sys.stdout.write(json.dumps(update) + "\n")
        sys.stdout.flush()

        current_status = "active"  # 恢复空闲
        return {"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}}

    elif method == "session/cancel":
        session_id = params.get("sessionId")
        log(f"取消会话: {session_id}")
        current_status = "active"
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "not found"}}


# ============================================================
#  主循环
# ============================================================

def main():
    log(f"启动中 (v{AGENT_VERSION})...")

    # 注册到 Registry
    register()

    # 启动心跳线程
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    log("心跳线程已启动 (间隔 10s)")

    log("等待 stdin 输入...")

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = handle_request(req)
                if resp:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                log(f"错误: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        unregister()
        log("已退出")


if __name__ == "__main__":
    main()

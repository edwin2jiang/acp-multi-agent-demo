#!/usr/bin/env python3
"""
Agent A - Python 代码专家
ACP Agent 实现，支持 JSON-RPC 协议
"""

import json
import sys
import time
import requests

AGENT_ID = "python-agent"
AGENT_NAME = "Python Agent"
AGENT_DESC = "擅长 Python 代码编写和调试"
REGISTRY_URL = "http://127.0.0.1:3000"

# 存储会话
sessions = {}
session_counter = 0


def log(msg):
    print(f"[{AGENT_NAME}] {msg}", file=sys.stderr)


def register_to_registry():
    """向注册中心注册自己"""
    try:
        resp = requests.post(f"{REGISTRY_URL}/register", json={
            "id": AGENT_ID,
            "name": AGENT_NAME,
            "description": AGENT_DESC,
            "capabilities": ["python", "debugging", "refactoring"]
        })
        if resp.status_code == 200:
            log(f"注册成功")
        else:
            log(f"注册失败: {resp.status_code}")
    except Exception as e:
        log(f"注册失败: {e}")


def unregister_from_registry():
    """从注册中心注销"""
    try:
        requests.post(f"{REGISTRY_URL}/unregister", json={"id": AGENT_ID})
        log("已注销")
    except:
        pass


def handle_request(req):
    """处理 JSON-RPC 请求"""
    global session_counter
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "agentInfo": {"name": AGENT_NAME, "version": "1.0.0"}
            }
        }
    
    elif method == "session/new":
        session_counter += 1
        session_id = f"py_{session_counter:03d}"
        sessions[session_id] = {"cwd": params.get("cwd", "/tmp")}
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
        
        log(f"处理 prompt: {text[:40]}")
        
        # 模拟 LLM 处理
        time.sleep(0.5)
        
        # 返回 Python 相关的响应
        response = f"我是 {AGENT_NAME}，擅长 Python。你说的 '{text}' 我来帮你处理..."
        
        update = {
            "jsonrpc": "2.0",
            "method": "session/update",
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
        
        return {"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}}
    
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "not found"}}


def main():
    log("启动中...")
    register_to_registry()
    log("等待输入...")
    
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
        unregister_from_registry()
        log("已退出")


if __name__ == "__main__":
    main()

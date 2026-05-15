#!/usr/bin/env python3
"""
会随机崩溃的 Agent（用于测试重连机制）
"""
import json
import sys
import time
import random

sessions = {}
counter = 0

def log(msg):
    print(f"[Agent] {msg}", file=sys.stderr)

log("启动中...")

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    
    try:
        req = json.loads(line)
        method = req.get("method", "")
        req_id = req.get("id")
        params = req.get("params", {})
        
        # 模拟随机崩溃（20% 概率）
        if random.random() < 0.2 and method == "session/prompt":
            log("模拟崩溃!")
            sys.exit(1)
        
        if method == "initialize":
            resp = {"jsonrpc":"2.0","id":req_id,"result":{
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
                "agentInfo": {"name": "crashy-agent", "version": "1.0"}
            }}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        
        elif method == "session/new":
            counter += 1
            sid = f"sess_{counter:03d}"
            sessions[sid] = {"cwd": params.get("cwd", "/tmp")}
            log(f"新会话: {sid}")
            resp = {"jsonrpc":"2.0","id":req_id,"result":{"sessionId": sid}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        
        elif method == "session/prompt":
            sid = params.get("sessionId")
            prompt = params.get("prompt", [])
            text = ""
            for p in prompt:
                if isinstance(p, dict) and p.get("type") == "text":
                    text = p.get("text", "")
                    break
            
            log(f"处理: {text[:30]}")
            time.sleep(0.3)
            
            update = {"jsonrpc":"2.0","method":"session/update","params":{
                "sessionId": sid,
                "update": {"sessionUpdate":"agent_message_chunk",
                          "content":{"type":"text","text":f"响应: {text}"}}
            }}
            sys.stdout.write(json.dumps(update) + "\n")
            sys.stdout.flush()
            
            resp = {"jsonrpc":"2.0","id":req_id,"result":{"stopReason":"end_turn"}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        
        elif method == "session/resume":
            sid = params.get("sessionId")
            log(f"恢复会话: {sid}")
            resp = {"jsonrpc":"2.0","id":req_id,"result":{}}
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    
    except Exception as e:
        log(f"错误: {e}")

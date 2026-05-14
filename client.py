#!/usr/bin/env python3
"""
ACP Client - 演示如何发现和连接多个 Agent

核心流程：
1. 查询 Registry 获取可用 Agent 列表
2. 根据需求选择合适的 Agent
3. 直接启动 Agent 子进程并连接 stdin/stdout
"""

import json
import subprocess
import time
import requests
import sys
import os


REGISTRY_URL = "http://127.0.0.1:3000"


def log(msg):
    print(f"[Client] {msg}")


def discover_agents():
    """从 Registry 发现可用 Agent"""
    log("查询 Registry 获取 Agent 列表...")
    try:
        resp = requests.get(f"{REGISTRY_URL}/agents")
        agents = resp.json().get("agents", [])
        log(f"发现 {len(agents)} 个 Agent:")
        for a in agents:
            print(f"  - {a['name']} ({a['id']})")
            print(f"    描述: {a['description']}")
            print(f"    能力: {', '.join(a.get('capabilities', []))}")
        return agents
    except Exception as e:
        log(f"查询失败: {e}")
        return []


def select_agent(agents, task_type):
    """根据任务类型选择 Agent"""
    # 简单匹配逻辑
    if "python" in task_type.lower():
        for a in agents:
            if "python" in a.get("capabilities", []):
                return a
    elif "rust" in task_type.lower():
        for a in agents:
            if "rust" in a.get("capabilities", []):
                return a
    
    # 默认返回第一个
    return agents[0] if agents else None


def connect_to_agent(agent_info):
    """直接启动 Agent 子进程（本地模式）"""
    agent_id = agent_info["id"]
    log(f"连接 Agent: {agent_info['name']} ({agent_id})")
    
    # 根据 agent_id 选择脚本
    script_map = {
        "python-agent": "agent_a.py",
        "rust-agent": "agent_b.py"
    }
    script = script_map.get(agent_id)
    if not script:
        log(f"未知 Agent: {agent_id}")
        return None
    
    script_path = os.path.join(os.path.dirname(__file__), script)
    
    # 启动 Agent 子进程
    proc = subprocess.Popen(
        ["python3", script_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )
    
    log(f"Agent 进程启动 (PID: {proc.pid})")
    return proc


def send_to_agent(proc, method, params):
    """向 Agent 发送 JSON-RPC 请求"""
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    
    line = proc.stdout.readline()
    if line:
        return json.loads(line)
    return None


def main():
    print("=" * 60)
    print("  ACP Client Demo")
    print("  演示：发现 Agent → 选择 Agent → 连接 Agent")
    print("=" * 60)
    
    # 1. 发现 Agent
    agents = discover_agents()
    if not agents:
        print("\n[!] 没有发现可用 Agent，请先启动 Registry 和 Agent")
        return
    
    # 2. 根据任务选择 Agent
    print("\n" + "-" * 60)
    print("  选择 Agent")
    print("-" * 60)
    
    # 模拟不同任务
    tasks = [
        ("写一个 Python 快速排序", "python"),
        ("优化 Rust 的内存分配", "rust"),
    ]
    
    for task_text, task_type in tasks:
        print(f"\n任务: {task_text}")
        agent = select_agent(agents, task_type)
        if not agent:
            print("  没有合适的 Agent")
            continue
        
        print(f"  选择: {agent['name']}")
        
        # 3. 连接 Agent
        proc = connect_to_agent(agent)
        if not proc:
            continue
        
        # 4. 初始化
        resp = send_to_agent(proc, "initialize", {
            "protocolVersion": 1,
            "clientInfo": {"name": "demo-client", "version": "1.0"}
        })
        print(f"  初始化: {'OK' if resp else 'FAIL'}")
        
        # 5. 创建会话
        resp = send_to_agent(proc, "session/new", {"cwd": "/tmp"})
        session_id = resp.get("result", {}).get("sessionId") if resp else None
        print(f"  会话: {session_id}")
        
        # 6. 发送 prompt
        resp = send_to_agent(proc, "session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": task_text}]
        })
        print(f"  响应: {'end_turn' if resp and resp.get('result', {}).get('stopReason') == 'end_turn' else 'error'}")
        
        # 7. 关闭
        proc.stdin.close()
        proc.terminate()
        print(f"  连接已关闭")
    
    # 总结
    print("\n" + "=" * 60)
    print("  总结")
    print("=" * 60)
    print("""
Client 连接 Agent 的方式：

本地模式（当前）：
  1. 查询 Registry 获取 Agent 列表
  2. 根据任务类型选择 Agent
  3. 直接启动 Agent 子进程
  4. 通过 stdin/stdout 通信

远程模式（开发中）：
  1. 查询 Registry 获取 Agent 列表
  2. 根据任务类型选择 Agent
  3. HTTP 连接到 Agent 的地址
  4. 通过 HTTP 通信

关键区别：
  - 本地模式：Client 启动 Agent 进程，天然知道连接谁
  - 远程模式：Agent 独立运行，需要 Registry 来发现
""")


if __name__ == "__main__":
    main()

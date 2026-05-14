#!/usr/bin/env python3
"""
一键运行 ACP Demo

演示完整的流程：
1. 启动 Registry
2. 启动多个 Agent（自动注册）
3. Client 查询 Registry 并连接 Agent
"""

import subprocess
import time
import sys
import os
import signal
import requests


REGISTRY_PORT = 3000
REGISTRY_URL = f"http://127.0.0.1:{REGISTRY_PORT}"


def wait_for_registry(timeout=5):
    """等待 Registry 启动"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{REGISTRY_URL}/agents", timeout=1)
            if resp.status_code == 200:
                return True
        except:
            pass
        time.sleep(0.1)
    return False


def main():
    print("=" * 60)
    print("  ACP 多 Agent 完整演示")
    print("=" * 60)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    processes = []
    
    try:
        # 1. 启动 Registry
        print("\n[1/3] 启动 Registry...")
        registry = subprocess.Popen(
            [sys.executable, os.path.join(script_dir, "registry.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes.append(("Registry", registry))
        
        if not wait_for_registry():
            print("[!] Registry 启动失败")
            return
        print("    Registry 已启动")
        
        # 2. 启动 Agent A (Python Agent)
        print("\n[2/3] 启动 Agent...")
        agent_a = subprocess.Popen(
            [sys.executable, os.path.join(script_dir, "agent_a.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        processes.append(("Agent A", agent_a))
        time.sleep(0.5)
        print("    Python Agent 已启动并注册")
        
        # 3. 启动 Agent B (Rust Agent)
        agent_b = subprocess.Popen(
            [sys.executable, os.path.join(script_dir, "agent_b.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        processes.append(("Agent B", agent_b))
        time.sleep(0.5)
        print("    Rust Agent 已启动并注册")
        
        # 4. 查看 Registry 中的 Agent
        print("\n[3/3] Client 查询 Registry...")
        resp = requests.get(f"{REGISTRY_URL}/agents")
        agents = resp.json().get("agents", [])
        
        print(f"\n    Registry 中有 {len(agents)} 个 Agent:")
        for a in agents:
            print(f"      [{a['id']}] {a['name']}: {a['description']}")
        
        # 5. 演示 Client 如何选择 Agent
        print("\n" + "-" * 60)
        print("  演示：Client 根据任务选择 Agent")
        print("-" * 60)
        
        tasks = [
            ("写一个 Python 快速排序", "python"),
            ("优化 Rust 的内存分配", "rust"),
        ]
        
        for task, task_type in tasks:
            print(f"\n  任务: {task}")
            
            # 选择 Agent
            selected = None
            for a in agents:
                if task_type in a.get("capabilities", []):
                    selected = a
                    break
            
            if selected:
                print(f"  选择: {selected['name']} (擅长: {', '.join(selected['capabilities'])})")
            else:
                print("  没有合适的 Agent")
        
        # 6. 总结
        print("\n" + "=" * 60)
        print("  完整流程演示完成")
        print("=" * 60)
        print("""
演示的流程：

  ┌─────────┐          ┌──────────────┐          ┌─────────────┐
  │ Registry │ <─────── │  Agent A     │          │  Agent B    │
  │  :3000   │          │  (Python)    │          │  (Rust)     │
  └─────────┘          └──────────────┘          └─────────────┘
       ▲                       ▲                        ▲
       │                       │                        │
       │  POST /register       │  POST /register        │
       └───────────────────────┴────────────────────────┘
       
  1. Agent 启动时 POST /register 注册到 Registry
  2. Client GET /agents 查询可用 Agent
  3. Client 根据任务类型选择 Agent
  4. Client 直接启动选中的 Agent 子进程
  5. Client 通过 stdin/stdout 与 Agent 通信

关键洞察：
  - 本地模式：Client 启动 Agent 进程，不需要 Registry
    （但有了 Registry 可以知道有哪些 Agent 可用）
  - 远程模式：Agent 独立运行，必须通过 Registry 发现
  - ACP 的 Registry 类似 DNS：告诉你"在哪里"，但不负责通信
""")
        
        print("按 Enter 退出...")
        input()
        
    except KeyboardInterrupt:
        pass
    finally:
        print("\n清理进程...")
        for name, proc in processes:
            try:
                proc.terminate()
                print(f"  {name} 已停止")
            except:
                pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One-command demo for ACP standalone worker pools.

All workers have the same capabilities. The client does not route by task type;
it routes by conversation affinity because each ACP stdio connection is a
standalone, single-lane channel.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from acp_demo.pool_client import StickyConversationPool, WorkerHandle


REGISTRY_PORT = 3000
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://127.0.0.1:{REGISTRY_PORT}")


def wait_for_registry(timeout: float = 5) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{REGISTRY_URL}/health", timeout=1)
            if response.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def wait_for_agents(count: int, timeout: float = 5) -> list[dict]:
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{REGISTRY_URL}/agents", timeout=1)
            agents = response.json().get("agents", [])
            if len(agents) >= count:
                return agents
        except Exception:
            pass
        time.sleep(0.1)
    return []


def start_process(label: str, command: list[str], env: dict | None = None, **kwargs) -> subprocess.Popen:
    process = subprocess.Popen(command, text=True, bufsize=1, env=env, **kwargs)
    print(f"    {label} 已启动 (PID: {process.pid})")
    return process


def update_text(result: dict) -> str:
    chunks = []
    for update in result["updates"]:
        text = update.get("params", {}).get("update", {}).get("content", {}).get("text")
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ACP sticky-session worker-pool demo.")
    parser.add_argument("--workers", type=int, default=3, help="启动多少个完全同能力的 standalone ACP worker")
    parser.add_argument("--keep-alive", action="store_true", help="演示结束后保持 Registry/Worker 运行")
    args = parser.parse_args()

    print("=" * 72)
    print("  ACP standalone 多会话并发 Demo")
    print("=" * 72)
    print("  模型: 多个同能力 worker + Client 维护 conversation_id -> worker 的粘性映射")

    root_dir = Path(__file__).resolve().parents[2]
    processes: list[tuple[str, subprocess.Popen]] = []
    worker_handles: list[WorkerHandle] = []

    try:
        print("\n[1/5] 启动 Registry（只做 worker 目录和健康观察，不参与对话转发）...")
        registry = start_process(
            "Registry",
            [sys.executable, "-m", "acp_demo.registry"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(("Registry", registry))
        if not wait_for_registry():
            print("[!] Registry 启动失败")
            return

        print(f"\n[2/5] 启动 {args.workers} 个完全同能力 ACP standalone worker...")
        for index in range(1, args.workers + 1):
            worker_id = f"worker-{index}"
            env = os.environ.copy()
            env["ACP_WORKER_ID"] = worker_id
            env["ACP_WORKER_NAME"] = f"ACP Worker {index}"
            process = start_process(
                f"Worker {index}",
                [sys.executable, "-m", "acp_demo.worker_agent"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            processes.append((worker_id, process))
            worker_handles.append(WorkerHandle(worker_id, process))
            time.sleep(0.15)

        agents = wait_for_agents(args.workers)
        print("\n[3/5] Registry 中的 worker manifest（注意 capabilities 完全一样）:")
        for agent in agents:
            print(f"    [{agent['id']}] {agent['name']} capabilities={agent.get('capabilities', [])}")

        pool = StickyConversationPool(worker_handles, cwd=str(root_dir))

        print("\n[4/5] 模拟多个 conversation 并发发送消息...")
        conversation_rounds = [
            ("chat-alpha", "第一轮：帮我看一下这个 Python 报错"),
            ("chat-beta", "第一轮：解释一下 ACP standalone 为什么不能复用"),
            ("chat-gamma", "第一轮：写一个最小 JSON-RPC 请求"),
            ("chat-alpha", "第二轮：沿着刚才那个报错继续分析"),
            ("chat-beta", "第二轮：继续刚才的架构讨论"),
            ("chat-delta", "第一轮：新开一个会话"),
        ]

        results = []
        started_at = time.time()
        with ThreadPoolExecutor(max_workers=min(args.workers, len(conversation_rounds))) as executor:
            futures = [
                executor.submit(pool.prompt, conversation_id, prompt)
                for conversation_id, prompt in conversation_rounds
            ]
            for future in as_completed(futures):
                results.append(future.result())
        elapsed = time.time() - started_at

        for result in sorted(results, key=lambda item: (item["conversation_id"], item["acp_session_id"])):
            print(f"\n  conversation={result['conversation_id']}")
            print(f"    sticky worker: {result['worker_id']}")
            print(f"    acp session: {result['acp_session_id']}")
            for line in update_text(result).splitlines():
                print(f"    {line}")

        print("\n[5/5] Client 侧粘性映射表:")
        for conversation_id, worker_id in pool.assignment_snapshot().items():
            print(f"    {conversation_id} -> {worker_id}")

        health = requests.get(f"{REGISTRY_URL}/health", timeout=3).json()
        print(f"\nRegistry health: status={health['status']}, agents_total={health['agents_total']}")
        print(f"并发演示耗时: {elapsed:.2f}s")

        print("\n" + "=" * 72)
        print("  演示完成")
        print("=" * 72)
        print("  关键点: 同一个 conversation 后续消息回到同一个 worker；不同 conversation 可以落到不同 worker 并发处理。")

        if args.keep_alive:
            print("\n保持运行中。按 Ctrl+C 退出...")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        print("\n清理进程...")
        for name, process in reversed(processes):
            try:
                process.terminate()
                process.wait(timeout=3)
                print(f"  {name} 已停止")
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()

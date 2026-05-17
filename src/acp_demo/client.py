#!/usr/bin/env python3
"""Small standalone client demo for sticky conversation routing."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from acp_demo.pool_client import StickyConversationPool, WorkerHandle


def start_worker(index: int) -> WorkerHandle:
    worker_id = f"worker-{index}"
    env = os.environ.copy()
    env["ACP_WORKER_ID"] = worker_id
    env["ACP_WORKER_NAME"] = f"ACP Worker {index}"
    process = subprocess.Popen(
        [sys.executable, "-m", "acp_demo.worker_agent"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )
    time.sleep(0.15)
    return WorkerHandle(worker_id, process)


def main() -> None:
    print("=" * 60)
    print("  Sticky ACP Client Demo")
    print("=" * 60)

    workers = [start_worker(1), start_worker(2)]
    pool = StickyConversationPool(workers, cwd=str(Path.cwd()))

    try:
        for conversation_id, text in [
            ("chat-a", "第一轮：你好"),
            ("chat-b", "第一轮：另一个会话"),
            ("chat-a", "第二轮：继续刚才的话题"),
        ]:
            result = pool.prompt(conversation_id, text)
            print(f"\nconversation={conversation_id}")
            print(f"  worker={result['worker_id']}")
            print(f"  acp_session={result['acp_session_id']}")

        print("\n粘性映射:")
        for conversation_id, worker_id in pool.assignment_snapshot().items():
            print(f"  {conversation_id} -> {worker_id}")
    finally:
        for worker in workers:
            worker.process.terminate()
            worker.process.wait(timeout=3)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Minimal ACP stdio connection smoke test.

Run from the repository root:

    python3 examples/hermes_acp_connection_smoke.py

This script launches one local demo ACP worker, opens the stdio JSON-RPC
connection, initializes it, creates a session, and sends two simple prompts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class AcpStdioConnection:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.next_id = 0

    def request(self, method: str, params: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self.next_id += 1
        request_id = self.next_id
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

        updates: list[dict[str, Any]] = []
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("ACP worker closed stdout before replying")

            response = json.loads(line)
            if "method" in response:
                updates.append(response)
                continue

            if response.get("id") == request_id:
                return response, updates


def start_local_worker() -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["ACP_WORKER_ID"] = "hermes-smoke-worker"
    env["ACP_WORKER_NAME"] = "Hermes Smoke Worker"
    env["REGISTRY_URL"] = "http://127.0.0.1:9"
    env["ACP_PROMPT_DELAY"] = "0.05"
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{env.get('PYTHONPATH', '')}"

    return subprocess.Popen(
        [sys.executable, "-m", "acp_demo.worker_agent"],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        env=env,
    )


def print_response(title: str, response: dict[str, Any], updates: list[dict[str, Any]]) -> None:
    print(f"\n== {title} ==")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    for update in updates:
        print("\n-- session/update --")
        print(json.dumps(update, ensure_ascii=False, indent=2))


def main() -> None:
    worker = start_local_worker()
    connection = AcpStdioConnection(worker)

    try:
        initialize, updates = connection.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientInfo": {"name": "simple-hermes-acp-client", "version": "0.1.0"},
            },
        )
        print_response("initialize", initialize, updates)

        session, updates = connection.request(
            "session/new",
            {
                "cwd": str(ROOT),
                "conversationId": "hello-hermes",
            },
        )
        print_response("session/new", session, updates)
        session_id = session["result"]["sessionId"]

        for text in ["你好，我在测试 ACP connection。", "再发一条消息，确认 session 还在。"]:
            response, updates = connection.request(
                "session/prompt",
                {
                    "sessionId": session_id,
                    "prompt": [{"type": "text", "text": text}],
                },
            )
            print_response(f"session/prompt: {text}", response, updates)

    finally:
        worker.terminate()
        try:
            worker.wait(timeout=3)
        except subprocess.TimeoutExpired:
            worker.kill()


if __name__ == "__main__":
    main()

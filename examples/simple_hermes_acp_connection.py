#!/usr/bin/env python3
"""One-file client for talking to `hermes acp --accept-hooks` over ACP stdio.

Run:

    python3 examples/simple_hermes_acp_connection.py "你好，确认一下连接是否成功"

The script starts Hermes ACP as a subprocess, sends initialize, creates one
session, sends one prompt, prints session/update chunks, then exits.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


class AcpClient:
    def __init__(self, command: list[str], cwd: str) -> None:
        self.command = command
        self.cwd = cwd
        self.process: subprocess.Popen[str] | None = None
        self.incoming: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()
        self.next_id = 0

    def start(self) -> None:
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def request(self, method: str, params: dict[str, Any], timeout: float = 60) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not self.process:
            self.start()
        assert self.process is not None and self.process.stdin is not None

        self.next_id += 1
        request_id = self.next_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

        updates: list[dict[str, Any]] = []
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"timeout waiting for response id={request_id}")

            item = self.incoming.get(timeout=remaining)
            if item is None:
                raise RuntimeError("Hermes ACP process exited")
            if isinstance(item, BaseException):
                raise RuntimeError(f"failed to read Hermes ACP stdout: {item}") from item

            if item.get("id") == request_id:
                return item, updates

            if "method" in item and "id" in item:
                self._reply_to_agent_request(item)
            else:
                updates.append(item)

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                if line.strip():
                    self.incoming.put(json.loads(line))
        except BaseException as exc:
            self.incoming.put(exc)
        finally:
            self.incoming.put(None)

    def _reply_to_agent_request(self, request: dict[str, Any]) -> None:
        assert self.process is not None and self.process.stdin is not None
        request_id = request.get("id")
        method = request.get("method")

        if method == "session/request_permission":
            response = {"jsonrpc": "2.0", "id": request_id, "result": {"outcome": {"outcome": "cancelled"}}}
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"client method not implemented: {method}"},
            }

        self.process.stdin.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()


def extract_text(updates: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in updates:
        update = message.get("params", {}).get("update", {})
        content = update.get("content") or update.get("chunk") or {}
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            parts.append(content["text"])
    return "".join(parts)


def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "你好，确认一下 ACP connection 是否成功。"
    cwd = str(Path.cwd())
    client = AcpClient(["hermes", "acp", "--accept-hooks"], cwd)

    try:
        init, _ = client.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                },
                "clientInfo": {"name": "simple-python-acp-client", "version": "0.1.0"},
            },
        )
        print("initialize:")
        print(json.dumps(init, ensure_ascii=False, indent=2))

        session, _ = client.request("session/new", {"cwd": cwd, "mcpServers": []})
        session_id = session["result"]["sessionId"]
        print(f"\nsessionId: {session_id}")

        response, updates = client.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": prompt}]},
            timeout=180,
        )

        text = extract_text(updates)
        if text:
            print("\nagent text:")
            print(text)

        print("\nfinal response:")
        print(json.dumps(response, ensure_ascii=False, indent=2))

    finally:
        client.stop()


if __name__ == "__main__":
    main()

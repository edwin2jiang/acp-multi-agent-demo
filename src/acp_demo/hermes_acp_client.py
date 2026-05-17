#!/usr/bin/env python3
"""ACP client/launcher for talking to Hermes Agent over stdio."""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_HERMES_COMMAND = ["hermes", "acp", "--accept-hooks"]


@dataclass
class AcpExchange:
    response: dict | None
    updates: list[dict] = field(default_factory=list)
    client_requests: list[dict] = field(default_factory=list)


class HermesAcpClient:
    """Launches an ACP agent subprocess and speaks newline-delimited JSON-RPC."""

    def __init__(
        self,
        command: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ):
        self.command = command or DEFAULT_HERMES_COMMAND
        self.cwd = str(Path(cwd or Path.cwd()).resolve())
        self.env = env or os.environ.copy()
        self.process: subprocess.Popen | None = None
        self.message_id = 0
        self.lock = threading.Lock()
        self.incoming: queue.Queue[dict | BaseException | None] = queue.Queue()
        self.reader_thread: threading.Thread | None = None

    def start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.incoming = queue.Queue()
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=self.cwd,
            env=self.env,
        )
        self.reader_thread = threading.Thread(target=self._read_stdout_loop, daemon=True)
        self.reader_thread.start()

    def stop(self) -> None:
        if not self.process:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe:
                pipe.close()

    def initialize(self) -> AcpExchange:
        return self.send("initialize", {
            "protocolVersion": 1,
            "clientCapabilities": {
                "fs": {"readTextFile": False, "writeTextFile": False},
                "terminal": False,
            },
            "clientInfo": {"name": "acp-hermes-demo", "version": "1.0.0"},
        })

    def new_session(self, mcp_servers: list[dict] | None = None) -> AcpExchange:
        return self.send("session/new", {
            "cwd": self.cwd,
            "mcpServers": mcp_servers or [],
        })

    def prompt(self, session_id: str, text: str) -> AcpExchange:
        return self.send("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": text}],
        }, timeout=120)

    def send(self, method: str, params: dict, timeout: float = 30) -> AcpExchange:
        self.start()
        assert self.process is not None
        if self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("ACP subprocess stdio pipes are unavailable")

        with self.lock:
            self.message_id += 1
            request_id = self.message_id
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
            self.process.stdin.write(json.dumps(request, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            return self._read_until_response(request_id, timeout)

    def stderr_tail(self, limit: int = 4000) -> str:
        if not self.process or not self.process.stderr:
            return ""
        try:
            return self.process.stderr.read()[-limit:]
        except Exception:
            return ""

    def _read_until_response(self, request_id: int, timeout: float) -> AcpExchange:
        updates: list[dict] = []
        client_requests: list[dict] = []
        deadline = time.time() + timeout

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for ACP response id={request_id}")
            try:
                item = self.incoming.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f"timed out waiting for ACP response id={request_id}") from exc
            if item is None:
                raise RuntimeError(f"ACP subprocess exited before response id={request_id}")
            if isinstance(item, BaseException):
                raise RuntimeError(f"failed to read ACP message: {item}") from item

            message = item
            if "id" in message and message.get("id") == request_id:
                return AcpExchange(response=message, updates=updates, client_requests=client_requests)

            if "method" in message and "id" in message:
                client_requests.append(message)
                self._respond_to_agent_request(message)
                continue

            if "method" in message:
                updates.append(message)
                continue

            updates.append(message)

    def _read_stdout_loop(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            for line in self.process.stdout:
                if line.strip():
                    self.incoming.put(json.loads(line))
        except BaseException as exc:
            self.incoming.put(exc)
        finally:
            self.incoming.put(None)

    def _respond_to_agent_request(self, request: dict) -> None:
        assert self.process is not None and self.process.stdin is not None
        request_id = request.get("id")
        method = request.get("method", "")

        if method == "session/request_permission":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"outcome": {"outcome": "cancelled"}},
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"client method not supported by demo: {method}",
                },
            }
        self.process.stdin.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()


def text_from_updates(updates: list[dict], session_update: str = "agent_message_chunk") -> str:
    chunks = []
    for message in updates:
        update = message.get("params", {}).get("update", {})
        if update.get("sessionUpdate") != session_update:
            continue
        content = update.get("content") or update.get("chunk") or {}
        text = content.get("text")
        if text:
            chunks.append(text)
    return "".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch Hermes in ACP mode and send a prompt.")
    parser.add_argument("--cwd", default=str(Path.cwd()), help="ACP session working directory")
    parser.add_argument("--prompt", help="Prompt text to send after creating a session")
    parser.add_argument(
        "--command",
        nargs="+",
        default=DEFAULT_HERMES_COMMAND,
        help="ACP agent command. Default: hermes acp --accept-hooks",
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON responses")
    args = parser.parse_args()

    client = HermesAcpClient(command=args.command, cwd=args.cwd)
    try:
        init = client.initialize()
        session = client.new_session()
        session_id = session.response["result"]["sessionId"]

        if args.json:
            print(json.dumps({"initialize": init.response, "session": session.response}, ensure_ascii=False, indent=2))
        else:
            info = init.response["result"].get("agentInfo", {})
            print(f"Connected to {info.get('name', 'agent')} v{info.get('version', '?')}")
            print(f"ACP session: {session_id}")

        if args.prompt:
            result = client.prompt(session_id, args.prompt)
            if args.json:
                print(json.dumps({
                    "prompt": result.response,
                    "updates": result.updates,
                    "client_requests": result.client_requests,
                }, ensure_ascii=False, indent=2))
            else:
                text = text_from_updates(result.updates)
                if text:
                    print("\nAgent response:")
                    print(text)
                print(f"\nStop reason: {result.response['result'].get('stopReason')}")
    finally:
        client.stop()


if __name__ == "__main__":
    main()

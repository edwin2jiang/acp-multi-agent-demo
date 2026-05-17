#!/usr/bin/env python3
"""Reusable stdin/stdout JSON-RPC runtime for demo ACP agents."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from copy import deepcopy

import requests

from acp_demo.skill_catalog import select_skills_for_prompt


REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://127.0.0.1:3000")
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "10"))


class StdioAgentRuntime:
    def __init__(self, manifest: dict):
        self.manifest = deepcopy(manifest)
        self.agent_id = self.manifest["id"]
        self.agent_name = self.manifest["name"]
        self.session_prefix = self.manifest.get("metadata", {}).get("session_prefix", "sess")
        self.response_style = self.manifest.get("metadata", {}).get("response_style", "处理请求")
        self.sessions: dict[str, dict] = {}
        self.session_counter = 0
        self.current_status = "active"
        self.running = True

    def log(self, message: str) -> None:
        print(f"[{self.agent_name}] {message}", file=sys.stderr, flush=True)

    def register(self) -> None:
        try:
            resp = requests.post(f"{REGISTRY_URL}/register", json=self.manifest, timeout=3)
            if resp.status_code == 200:
                self.log(f"注册成功 (id={self.agent_id}, v{self.manifest['version']})")
            else:
                self.log(f"注册失败: {resp.text}")
        except Exception as exc:
            self.log(f"注册失败: {exc}")

    def unregister(self) -> None:
        try:
            requests.post(f"{REGISTRY_URL}/unregister", json={"id": self.agent_id}, timeout=2)
            self.log("已注销")
        except Exception:
            pass

    def heartbeat_loop(self) -> None:
        while self.running:
            try:
                requests.post(
                    f"{REGISTRY_URL}/heartbeat",
                    json={"id": self.agent_id, "status": self.current_status},
                    timeout=3,
                )
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def _text_from_prompt(self, prompt: list) -> str:
        for part in prompt:
            if isinstance(part, dict) and part.get("type") == "text":
                return part.get("text", "")
        return ""

    def _response_text(self, prompt_text: str) -> str:
        skills = select_skills_for_prompt(self.manifest.get("skills", []), prompt_text)
        skill_names = ", ".join(skill["name"] for skill in skills) or "none"
        capabilities = ", ".join(self.manifest.get("capabilities", []))
        return (
            f"[{self.agent_name}] {self.response_style}: {prompt_text}\n"
            f"- 匹配能力: {capabilities}\n"
            f"- 选用 Skill: {skill_names}\n"
            f"- Demo 说明: 这里模拟 Agent 基于 manifest 中的 capabilities/skills 接手任务。"
        )

    def handle_request(self, request: dict) -> dict | None:
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": 1,
                    "agentCapabilities": {
                        "loadSession": True,
                        "sessionCapabilities": {"resume": {}, "close": {}},
                    },
                    "agentInfo": {
                        "name": self.agent_name,
                        "version": self.manifest["version"],
                        "description": self.manifest["description"],
                        "skills": self.manifest.get("skills", []),
                    },
                },
            }

        if method == "session/new":
            self.session_counter += 1
            session_id = f"{self.session_prefix}_{self.session_counter:03d}"
            self.sessions[session_id] = {
                "cwd": params.get("cwd", "/tmp"),
                "created_at": time.time(),
                "history": [],
            }
            self.log(f"新会话: {session_id}")
            return {"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": session_id}}

        if method == "session/resume":
            session_id = params.get("sessionId")
            self.sessions.setdefault(session_id, {"resumed_at": time.time(), "history": []})
            self.log(f"恢复会话: {session_id}")
            return {"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": session_id}}

        if method == "session/prompt":
            session_id = params.get("sessionId")
            prompt_text = self._text_from_prompt(params.get("prompt", []))
            self.sessions.setdefault(session_id, {"history": []})["history"].append(prompt_text)
            self.current_status = "busy"
            self.log(f"处理: {prompt_text[:48]}")

            time.sleep(0.25)
            update = {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": self._response_text(prompt_text)},
                    },
                },
            }
            self.write_message(update)
            self.current_status = "active"
            return {"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}}

        if method in {"session/cancel", "session/close"}:
            session_id = params.get("sessionId")
            self.sessions.pop(session_id, None)
            self.current_status = "active"
            self.log(f"关闭会话: {session_id}")
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }

    def write_message(self, message: dict) -> None:
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def serve_forever(self) -> None:
        self.log(f"启动中 (v{self.manifest['version']})...")
        self.register()
        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        heartbeat_thread.start()
        self.log(f"心跳线程已启动 (间隔 {HEARTBEAT_INTERVAL:g}s)")
        self.log("等待 stdin 输入...")

        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                    response = self.handle_request(request)
                    if response:
                        self.write_message(response)
                except Exception as exc:
                    self.log(f"错误: {exc}")
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            self.unregister()
            self.log("已退出")

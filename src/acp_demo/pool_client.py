#!/usr/bin/env python3
"""Sticky conversation routing for a pool of identical ACP stdio workers."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field


@dataclass
class WorkerHandle:
    worker_id: str
    process: subprocess.Popen
    message_id: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def send(self, method: str, params: dict) -> tuple[dict | None, list[dict]]:
        with self.lock:
            self.message_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self.message_id,
                "method": method,
                "params": params,
            }
            self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
            self.process.stdin.flush()

            updates = []
            while True:
                line = self.process.stdout.readline()
                if not line:
                    return None, updates
                message = json.loads(line)
                if "method" in message:
                    updates.append(message)
                    continue
                if message.get("id") == self.message_id:
                    return message, updates


@dataclass
class ConversationBinding:
    conversation_id: str
    worker: WorkerHandle
    acp_session_id: str


class StickyConversationPool:
    """Maps each conversation to exactly one standalone ACP worker process."""

    def __init__(self, workers: list[WorkerHandle], cwd: str):
        if not workers:
            raise ValueError("StickyConversationPool needs at least one worker")
        self.workers = workers
        self.cwd = cwd
        self.bindings: dict[str, ConversationBinding] = {}
        self.next_worker_index = 0
        self.assignment_lock = threading.Lock()

        for worker in self.workers:
            worker.send("initialize", {
                "protocolVersion": 1,
                "clientInfo": {"name": "sticky-pool-client", "version": "1.0.0"},
            })

    def _choose_worker_for_new_conversation(self) -> WorkerHandle:
        worker = self.workers[self.next_worker_index % len(self.workers)]
        self.next_worker_index += 1
        return worker

    def binding_for(self, conversation_id: str) -> ConversationBinding:
        with self.assignment_lock:
            existing = self.bindings.get(conversation_id)
            if existing:
                return existing

            worker = self._choose_worker_for_new_conversation()
            response, _ = worker.send("session/new", {
                "cwd": self.cwd,
                "conversationId": conversation_id,
            })
            session_id = response["result"]["sessionId"]
            binding = ConversationBinding(conversation_id, worker, session_id)
            self.bindings[conversation_id] = binding
            return binding

    def prompt(self, conversation_id: str, text: str) -> dict:
        binding = self.binding_for(conversation_id)
        response, updates = binding.worker.send("session/prompt", {
            "sessionId": binding.acp_session_id,
            "prompt": [{"type": "text", "text": text}],
        })
        return {
            "conversation_id": conversation_id,
            "worker_id": binding.worker.worker_id,
            "acp_session_id": binding.acp_session_id,
            "response": response,
            "updates": updates,
        }

    def assignment_snapshot(self) -> dict[str, str]:
        return {
            conversation_id: binding.worker.worker_id
            for conversation_id, binding in sorted(self.bindings.items())
        }

#!/usr/bin/env python3
"""Shared demo configuration for a pool of identical ACP workers."""

from __future__ import annotations


WORKER_MODULE = "acp_demo.worker_agent"

WORKER_CAPABILITIES = [
    "chat",
    "code",
    "reasoning",
    "tool-use",
]


def build_worker_manifest(
    worker_id: str = "worker-1",
    worker_name: str | None = None,
) -> dict:
    """Build the manifest used by every identical worker process."""
    return {
        "id": worker_id,
        "name": worker_name or f"ACP Worker {worker_id.split('-')[-1]}",
        "description": "同能力 ACP standalone worker；由 Client 按 conversation_id 做会话亲和路由",
        "version": "1.0.0",
        "capabilities": WORKER_CAPABILITIES,
        "skills": [],
        "input_content_types": ["text/plain", "application/json"],
        "output_content_types": ["text/plain", "application/json"],
        "transport": "stdio",
        "endpoint": None,
        "metadata": {
            "launch_command": ["python3", "-m", WORKER_MODULE],
            "module": WORKER_MODULE,
            "session_prefix": worker_id.replace("-", "_"),
            "routing": "sticky-conversation",
        },
    }

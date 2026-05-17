#!/usr/bin/env python3
"""Identical ACP standalone worker process."""

import os

from acp_demo.agent_runtime import StdioAgentRuntime
from acp_demo.demo_config import build_worker_manifest


def main() -> None:
    worker_id = os.environ.get("ACP_WORKER_ID", "worker-1")
    worker_name = os.environ.get("ACP_WORKER_NAME")
    StdioAgentRuntime(build_worker_manifest(worker_id, worker_name)).serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Python specialist Agent."""

import os

from acp_demo.agent_runtime import StdioAgentRuntime
from acp_demo.demo_config import build_manifest


def main() -> None:
    manifest = build_manifest(
        "python",
        agent_id=os.environ.get("ACP_AGENT_ID"),
        agent_name=os.environ.get("ACP_AGENT_NAME"),
    )
    StdioAgentRuntime(manifest).serve_forever()


if __name__ == "__main__":
    main()

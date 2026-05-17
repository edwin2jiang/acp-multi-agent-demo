#!/usr/bin/env python3
"""Shared demo configuration for all agents and clients."""

from __future__ import annotations

from acp_demo.skill_catalog import skills_for_agent


AGENT_DEFINITIONS = {
    "python": {
        "id": "python-agent",
        "name": "Python Agent",
        "description": "擅长 Python 代码编写、调试、重构和测试",
        "version": "1.1.0",
        "capabilities": ["python", "debugging", "refactoring", "testing"],
        "module": "acp_demo.agent_a",
        "session_prefix": "py",
        "response_style": "给出 Python 方向的实现建议",
    },
    "rust": {
        "id": "rust-agent",
        "name": "Rust Agent",
        "description": "擅长 Rust 代码编写、性能优化和系统编程",
        "version": "1.1.0",
        "capabilities": ["rust", "performance", "systems", "memory-safety"],
        "module": "acp_demo.agent_b",
        "session_prefix": "rs",
        "response_style": "给出 Rust 方向的实现建议",
    },
    "tooling": {
        "id": "skill-agent",
        "name": "Skill Agent",
        "description": "擅长选择现成 Skill、画流程图、解释工具链运作方式",
        "version": "1.0.0",
        "capabilities": ["skill-routing", "documentation", "diagram", "browser", "playwright"],
        "module": "acp_demo.agent_skill",
        "session_prefix": "sk",
        "response_style": "选择合适 Skill 并解释执行路径",
    },
}


def build_manifest(agent_kind: str, agent_id: str | None = None, agent_name: str | None = None) -> dict:
    definition = AGENT_DEFINITIONS[agent_kind]
    return {
        "id": agent_id or definition["id"],
        "name": agent_name or definition["name"],
        "description": definition["description"],
        "version": definition["version"],
        "capabilities": definition["capabilities"],
        "skills": skills_for_agent(agent_kind),
        "input_content_types": ["text/plain", "application/json"],
        "output_content_types": ["text/plain", "application/json"],
        "transport": "stdio",
        "endpoint": None,
        "metadata": {
            "launch_command": ["python3", "-m", definition["module"]],
            "module": definition["module"],
            "session_prefix": definition["session_prefix"],
            "response_style": definition["response_style"],
        },
    }


def module_for_agent_id(agent_id: str) -> str | None:
    normalized = agent_id.replace("-client", "")
    for definition in AGENT_DEFINITIONS.values():
        if normalized.startswith(definition["id"]):
            return definition["module"]
    return None

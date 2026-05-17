#!/usr/bin/env python3
"""
Small Skill catalog used by the demo agents.

The project keeps a few fallback Skill descriptions so the demo is portable,
and it also tries to discover existing Codex SKILL.md files from ~/.codex.
"""

from __future__ import annotations

from pathlib import Path


FALLBACK_SKILLS = {
    "openai-docs": {
        "name": "openai-docs",
        "title": "OpenAI Docs",
        "description": "Use official OpenAI documentation for API and model guidance.",
    },
    "playwright": {
        "name": "playwright",
        "title": "Playwright",
        "description": "Automate browser flows and verify UI behavior with screenshots.",
    },
    "browser": {
        "name": "browser",
        "title": "Browser",
        "description": "Open and inspect local web targets in the Codex in-app browser.",
    },
    "documents": {
        "name": "documents",
        "title": "Documents",
        "description": "Create, edit, render, and verify document artifacts.",
    },
    "spreadsheets": {
        "name": "spreadsheets",
        "title": "Spreadsheets",
        "description": "Create, analyze, format, and export spreadsheet artifacts.",
    },
    "python-testing": {
        "name": "python-testing",
        "title": "Python Testing",
        "description": "Plan and run focused Python tests for protocol and runtime behavior.",
    },
    "rust-performance": {
        "name": "rust-performance",
        "title": "Rust Performance",
        "description": "Review ownership, allocation, and performance tradeoffs in Rust code.",
    },
    "mermaid-diagrams": {
        "name": "mermaid-diagrams",
        "title": "Mermaid Diagrams",
        "description": "Explain system flows with readable Mermaid flowcharts and sequences.",
    },
}


def _candidate_skill_roots() -> list[Path]:
    home = Path.home()
    return [
        home / ".codex" / "skills",
        home / ".codex" / "plugins" / "cache",
    ]


def _extract_description(skill_md: Path) -> str:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    body_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        body_lines.append(stripped)
        if len(" ".join(body_lines)) > 220:
            break
    return " ".join(body_lines)[:260]


def _discover_local_skills() -> dict[str, dict]:
    discovered: dict[str, dict] = {}
    for root in _candidate_skill_roots():
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            skill_name = skill_md.parent.name
            description = _extract_description(skill_md)
            discovered[skill_name] = {
                "name": skill_name,
                "title": skill_name.replace("-", " ").title(),
                "description": description or f"Local Codex Skill from {skill_md.parent}",
                "source": "local-codex-skill",
                "path": str(skill_md),
            }
    return discovered


LOCAL_SKILLS = _discover_local_skills()


def get_skill(name: str) -> dict:
    fallback = FALLBACK_SKILLS.get(name, {
        "name": name,
        "title": name.replace("-", " ").title(),
        "description": "Demo Skill reference.",
    })
    skill = {**fallback, **LOCAL_SKILLS.get(name, {})}
    skill.setdefault("source", "demo-fallback")
    return skill


def skills_for_agent(agent_kind: str) -> list[dict]:
    if agent_kind == "python":
        names = ["python-testing", "openai-docs", "playwright"]
    elif agent_kind == "rust":
        names = ["rust-performance", "openai-docs"]
    elif agent_kind == "tooling":
        names = ["browser", "playwright", "documents", "spreadsheets", "mermaid-diagrams"]
    else:
        names = []
    return [get_skill(name) for name in names]


def select_skills_for_prompt(skills: list[dict], text: str) -> list[dict]:
    lowered = text.lower()
    selected = []
    for skill in skills:
        name = skill["name"].lower()
        title = skill.get("title", "").lower()
        description = skill.get("description", "").lower()
        tokens = set(name.replace("-", " ").split()) | set(title.split())
        if any(token in lowered for token in tokens if len(token) > 2):
            selected.append(skill)
        elif any(word in lowered for word in ["流程图", "diagram", "mermaid"]) and "mermaid" in name:
            selected.append(skill)
        elif "browser" in lowered and "browser" in name:
            selected.append(skill)
        elif "test" in lowered and ("testing" in name or "playwright" in name):
            selected.append(skill)
        elif "doc" in lowered and ("docs" in name or "documents" in name):
            selected.append(skill)

    return selected[:2] or skills[:1]

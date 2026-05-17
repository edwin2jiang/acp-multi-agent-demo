#!/usr/bin/env python3
"""
ACP Client - discover agents, select by capability/Skill, and talk over stdio.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import requests

from acp_demo.demo_config import module_for_agent_id


REGISTRY_URL = os.environ.get("REGISTRY_URL", "http://127.0.0.1:3000")


def log(message: str) -> None:
    print(f"[Client] {message}")


class AgentConnection:
    def __init__(self, agent_info: dict):
        self.agent_info = agent_info
        self.process: subprocess.Popen | None = None
        self.message_id = 0

    def connect(self) -> bool:
        module_name = module_for_agent_id(self.agent_info["id"])
        if not module_name:
            log(f"未知 Agent，无法找到启动脚本: {self.agent_info['id']}")
            return False

        child_id = f"{self.agent_info['id']}-client-{uuid.uuid4().hex[:6]}"
        env = os.environ.copy()
        env["ACP_AGENT_ID"] = child_id
        env["ACP_AGENT_NAME"] = f"{self.agent_info['name']} (client-owned)"

        self.process = subprocess.Popen(
            [sys.executable, "-m", module_name],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        log(f"已启动本地 stdio Agent: {module_name} (PID: {self.process.pid})")
        return True

    def close(self) -> None:
        if not self.process:
            return
        try:
            if self.process.stdin:
                self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=3)
        except Exception:
            self.process.kill()
        finally:
            log("连接已关闭")

    def send(self, method: str, params: dict) -> tuple[dict | None, list[dict]]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None, []

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


def discover_agents() -> list[dict]:
    log("查询 Registry 获取 Agent 列表...")
    try:
        response = requests.get(f"{REGISTRY_URL}/agents", timeout=3)
        response.raise_for_status()
        agents = response.json().get("agents", [])
    except Exception as exc:
        log(f"查询失败: {exc}")
        return []

    log(f"发现 {len(agents)} 个 Agent:")
    for agent in agents:
        skills = ", ".join(skill["name"] for skill in agent.get("skills", [])) or "none"
        print(f"  - {agent['name']} ({agent['id']})")
        print(f"    能力: {', '.join(agent.get('capabilities', []))}")
        print(f"    Skill: {skills}")
    return agents


def search_agents(capabilities: list[str] | None = None, skills: list[str] | None = None) -> list[dict]:
    payload = {"capabilities": capabilities or [], "skills": skills or []}
    response = requests.post(f"{REGISTRY_URL}/search", json=payload, timeout=3)
    response.raise_for_status()
    return response.json().get("agents", [])


def select_agent(agents: list[dict], task_type: str) -> dict | None:
    task_type = task_type.lower()
    for agent in agents:
        capabilities = agent.get("capabilities", [])
        skill_names = [skill.get("name", "") for skill in agent.get("skills", [])]
        if task_type in capabilities or task_type in skill_names:
            return agent
    return agents[0] if agents else None


def print_updates(updates: list[dict]) -> None:
    for update in updates:
        payload = update.get("params", {}).get("update", {})
        content = payload.get("content", {})
        text = content.get("text")
        if text:
            print("  流式 update:")
            for line in text.splitlines():
                print(f"    {line}")


def run_task(agent: dict, task_text: str) -> None:
    print(f"\n任务: {task_text}")
    print(f"  选择: {agent['name']}")

    connection = AgentConnection(agent)
    if not connection.connect():
        return

    try:
        response, _ = connection.send("initialize", {
            "protocolVersion": 1,
            "clientInfo": {"name": "demo-client", "version": "1.1.0"},
        })
        print(f"  初始化: {'OK' if response and 'result' in response else 'FAIL'}")

        response, _ = connection.send("session/new", {"cwd": str(Path.cwd())})
        session_id = response.get("result", {}).get("sessionId") if response else None
        print(f"  会话: {session_id}")

        response, updates = connection.send("session/prompt", {
            "sessionId": session_id,
            "prompt": [{"type": "text", "text": task_text}],
        })
        print_updates(updates)
        stop_reason = response.get("result", {}).get("stopReason") if response else "error"
        print(f"  最终响应: {stop_reason}")
    finally:
        connection.close()


def main() -> None:
    print("=" * 60)
    print("  ACP Client Demo")
    print("  发现 Agent -> 按能力/Skill 选择 -> stdio 通信")
    print("=" * 60)

    agents = discover_agents()
    if not agents:
        print("\n[!] 没有发现可用 Agent，请先运行: python3 -m acp_demo.run_demo --keep-alive")
        return

    tasks = [
        ("写一个 Python 快速排序并补测试", "python"),
        ("优化 Rust 的内存分配", "rust"),
        ("画一个 Mermaid 流程图解释 Agent 注册过程", "diagram"),
    ]

    for task_text, task_type in tasks:
        selected = select_agent(agents, task_type)
        if selected:
            run_task(selected, task_text)
        else:
            print(f"\n任务: {task_text}\n  没有合适的 Agent")


if __name__ == "__main__":
    main()

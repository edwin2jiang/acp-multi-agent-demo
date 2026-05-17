#!/usr/bin/env python3
"""
One-command ACP multi-agent demo.

Starts a Registry, three stdio agents, queries discovery/Skill endpoints,
then sends JSON-RPC messages to the selected agent processes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests


REGISTRY_PORT = 3000
REGISTRY_URL = os.environ.get("REGISTRY_URL", f"http://127.0.0.1:{REGISTRY_PORT}")


def wait_for_registry(timeout: float = 5) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{REGISTRY_URL}/health", timeout=1)
            if response.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.1)
    return False


def wait_for_agents(count: int, timeout: float = 5) -> list[dict]:
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(f"{REGISTRY_URL}/agents", timeout=1)
            agents = response.json().get("agents", [])
            if len(agents) >= count:
                return agents
        except Exception:
            pass
        time.sleep(0.1)
    return []


def send_rpc(process: subprocess.Popen, message_id: int, method: str, params: dict) -> tuple[dict | None, list[dict]]:
    request = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}
    process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
    process.stdin.flush()

    updates = []
    while True:
        line = process.stdout.readline()
        if not line:
            return None, updates
        message = json.loads(line)
        if "method" in message:
            updates.append(message)
            continue
        if message.get("id") == message_id:
            return message, updates


def select_agent(agents: list[dict], task_type: str) -> dict | None:
    for agent in agents:
        capabilities = agent.get("capabilities", [])
        skill_names = [skill.get("name") for skill in agent.get("skills", [])]
        if task_type in capabilities or task_type in skill_names:
            return agent
    return None


def print_update_text(updates: list[dict], indent: str = "    ") -> None:
    for update in updates:
        payload = update.get("params", {}).get("update", {})
        text = payload.get("content", {}).get("text")
        if not text:
            continue
        for line in text.splitlines():
            print(f"{indent}{line}")


def start_process(label: str, command: list[str], **kwargs) -> subprocess.Popen:
    process = subprocess.Popen(command, text=True, bufsize=1, **kwargs)
    print(f"    {label} 已启动 (PID: {process.pid})")
    return process


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ACP multi-agent demo.")
    parser.add_argument("--keep-alive", action="store_true", help="演示结束后保持 Registry/Agent 运行，方便另开终端跑 client")
    args = parser.parse_args()

    print("=" * 64)
    print("  ACP 多 Agent 完整演示")
    print("=" * 64)

    package_dir = Path(__file__).resolve().parent
    processes: list[tuple[str, subprocess.Popen]] = []

    try:
        print("\n[1/5] 启动 Registry...")
        registry = start_process(
            "Registry",
            [sys.executable, "-m", "acp_demo.registry"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(("Registry", registry))
        if not wait_for_registry():
            print("[!] Registry 启动失败")
            return

        print("\n[2/5] 启动 Agent 并注册 manifest...")
        agent_specs = [
            ("Python Agent", "acp_demo.agent_a"),
            ("Rust Agent", "acp_demo.agent_b"),
            ("Skill Agent", "acp_demo.agent_skill"),
        ]
        for label, module_name in agent_specs:
            process = start_process(
                label,
                [sys.executable, "-m", module_name],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            processes.append((label, process))
            time.sleep(0.2)

        agents = wait_for_agents(3)
        process_by_agent_id = {
            "python-agent": processes[1][1],
            "rust-agent": processes[2][1],
            "skill-agent": processes[3][1],
        }
        if len(agents) < 3:
            print(f"[!] 只发现 {len(agents)} 个 Agent，演示继续但结果可能不完整")

        print("\n[3/5] Client 查询 Registry...")
        for agent in agents:
            skills = ", ".join(skill["name"] for skill in agent.get("skills", [])) or "none"
            print(f"    [{agent['id']}] {agent['name']}")
            print(f"      capabilities: {', '.join(agent.get('capabilities', []))}")
            print(f"      skills: {skills}")

        skills_response = requests.get(f"{REGISTRY_URL}/skills", timeout=3).json()
        print(f"\n    Registry /skills 共发现 {skills_response['count']} 个 Skill:")
        for skill in skills_response["skills"]:
            agent_names = ", ".join(agent["name"] for agent in skill["agents"])
            print(f"      - {skill['name']} -> {agent_names}")

        print("\n[4/5] 根据任务选择 Agent，并通过 stdio 发送 JSON-RPC...")
        tasks = [
            ("写一个 Python 快速排序并补测试", "python"),
            ("优化 Rust 的内存分配", "rust"),
            ("画一个 Mermaid 流程图解释 Agent 注册过程", "diagram"),
        ]

        message_id = 0
        for task_text, task_type in tasks:
            selected = select_agent(agents, task_type)
            if not selected:
                print(f"\n  任务: {task_text}\n    没有找到匹配 Agent")
                continue

            process = process_by_agent_id[selected["id"]]
            print(f"\n  任务: {task_text}")
            print(f"    选择: {selected['name']}")

            message_id += 1
            response, _ = send_rpc(process, message_id, "initialize", {
                "protocolVersion": 1,
                "clientInfo": {"name": "run-demo", "version": "1.1.0"},
            })
            print(f"    initialize: {'OK' if response and 'result' in response else 'FAIL'}")

            message_id += 1
            response, _ = send_rpc(process, message_id, "session/new", {"cwd": str(package_dir.parent.parent)})
            session_id = response.get("result", {}).get("sessionId") if response else None
            print(f"    session: {session_id}")

            message_id += 1
            response, updates = send_rpc(process, message_id, "session/prompt", {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": task_text}],
            })
            print_update_text(updates)
            stop_reason = response.get("result", {}).get("stopReason") if response else "error"
            print(f"    final response: {stop_reason}")

        print("\n[5/5] Registry 健康检查...")
        health = requests.get(f"{REGISTRY_URL}/health", timeout=3).json()
        print(f"    status={health['status']}, agents_total={health['agents_total']}, active={health['agents_active']}")

        print("\n" + "=" * 64)
        print("  演示完成")
        print("=" * 64)
        print("  你刚才看到的是：注册 -> 发现 -> Skill/能力匹配 -> stdio JSON-RPC 通信。")
        print("  详细图解见 docs/architecture.md。")

        if args.keep_alive:
            print("\n保持运行中。另开终端可执行: python3 -m acp_demo.client")
            print("按 Ctrl+C 退出...")
            while True:
                time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        print("\n清理进程...")
        for name, process in reversed(processes):
            try:
                process.terminate()
                process.wait(timeout=3)
                print(f"  {name} 已停止")
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass


if __name__ == "__main__":
    main()

# ACP 多 Agent Demo

演示 ACP 协议中多个 Agent 的注册、发现和连接机制。

## 核心概念

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Client    │────>│  ACP Registry │<────│  Agent A        │
│  (编辑器)   │     │  (注册中心)   │     │  (Python Agent) │
└─────────────┘     └──────────────┘     └─────────────────┘
       │                    ^
       │                    │
       │             ┌─────────────────┐
       └────────────>│  Agent B        │
                     │  (Rust Agent)   │
                     └─────────────────┘

流程：
1. Agent 启动时向 Registry 注册自己
2. Client 向 Registry 查询可用 Agent
3. Client 直接连接目标 Agent 的 stdin/stdout
```

## 文件说明

- `agent_a.py` — Python Agent（擅长 Python 代码）
- `agent_b.py` — Rust Agent（擅长 Rust 代码）
- `registry.py` — ACP 注册中心
- `client.py` — 模拟 Client（连接多个 Agent）
- `run_demo.py` — 一键运行演示

## 运行

```bash
python3 run_demo.py
```

## ACP 的实际连接方式

### 本地模式（当前主流）
Client 直接启动 Agent 子进程：
```bash
# 编辑器（Client）直接 spawn Agent
agent_process = subprocess.Popen(
    ["python3", "agent_a.py"],
    stdin=PIPE, stdout=PIPE  # 通过管道连接
)
# 不需要注册中心，因为 Client 自己启动的 Agent
```

### 远程模式（开发中）
Agent 独立运行，Client 通过注册中心发现：
```bash
# Agent 先启动，向 Registry 注册
python3 agent_a.py --port 8001 &

# Client 查询 Registry，找到 Agent 的地址
curl http://registry:3000/agents
# → [{"name": "python-agent", "url": "http://localhost:8001"}, ...]

# Client 直连 Agent
client.connect("http://localhost:8001")
```

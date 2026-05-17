# ACP Demo 架构图解

这份文档用 Mermaid 图解释 demo 的运作原理。你可以把它当作读代码前的地图。

## 1. 总览

```mermaid
flowchart TB
    subgraph Agents["Agent 进程"]
        Python["Python Agent<br/>capabilities: python, testing<br/>skills: python-testing, openai-docs, playwright"]
        Rust["Rust Agent<br/>capabilities: rust, performance<br/>skills: rust-performance, openai-docs"]
        Skill["Skill Agent<br/>capabilities: documentation, diagram<br/>skills: browser, playwright, documents, spreadsheets, mermaid-diagrams"]
    end

    Registry["ACP Registry<br/>注册、发现、心跳、搜索"]
    Client["Client / Editor<br/>任务路由 + 会话管理"]

    Python -->|"POST /register"| Registry
    Rust -->|"POST /register"| Registry
    Skill -->|"POST /register"| Registry
    Python -.->|"POST /heartbeat"| Registry
    Rust -.->|"POST /heartbeat"| Registry
    Skill -.->|"POST /heartbeat"| Registry

    Client -->|"GET /agents"| Registry
    Client -->|"GET /skills"| Registry
    Client -->|"POST /search"| Registry
    Registry -->|"Agent manifest 列表"| Client

    Client ==>|"stdio JSON-RPC"| Python
    Client ==>|"stdio JSON-RPC"| Rust
    Client ==>|"stdio JSON-RPC"| Skill
```

## 2. 注册与发现

```mermaid
sequenceDiagram
    participant A as Agent
    participant R as Registry
    participant C as Client

    A->>R: POST /register<br/>id, name, capabilities, skills, transport
    R-->>A: registered
    loop every 10s
        A->>R: POST /heartbeat<br/>id, status
        R-->>A: ok
    end
    C->>R: GET /agents
    R-->>C: available agent manifests
    C->>R: GET /skills
    R-->>C: skills grouped by agent
```

Registry 保存的是“可发现信息”：Agent 名字、能力、Skill、transport、endpoint 或启动信息。它不转发对话内容。

## 3. Client 路由逻辑

```mermaid
flowchart LR
    Task["用户任务<br/>例如：画 Mermaid 流程图"]
    Extract["抽取需求标签<br/>diagram / documentation"]
    Search["Registry /search<br/>capabilities + skills"]
    Pick{"找到匹配 Agent?"}
    SkillAgent["Skill Agent"]
    Fallback["默认 Agent<br/>或提示无匹配"]
    Stdio["建立 stdio 连接"]

    Task --> Extract --> Search --> Pick
    Pick -- "yes" --> SkillAgent --> Stdio
    Pick -- "no" --> Fallback
```

在当前 demo 里，路由规则故意保持简单：任务类型命中 `capabilities` 或 `skills.name` 就选择该 Agent。真实系统可以把这里替换成 embedding 检索、策略引擎或模型路由器。

## 4. stdio JSON-RPC 会话

```mermaid
sequenceDiagram
    participant C as Client
    participant A as Selected Agent

    C->>A: initialize
    A-->>C: protocolVersion + agentInfo
    C->>A: session/new
    A-->>C: sessionId
    C->>A: session/prompt
    A-->>C: session/update<br/>agent_message_chunk
    A-->>C: response<br/>stopReason=end_turn
    C->>A: session/close
    A-->>C: ok
```

这里最容易踩坑的是 `session/prompt`：Agent 可以先发多个 `session/update`，最后才发和请求 `id` 对应的 response。Client 不能只读一行，而要持续读到匹配的 response 为止。

## 5. Skill 如何进入 manifest

```mermaid
flowchart TB
    Local["~/.codex/**/SKILL.md<br/>本机已有 Skill"]
    Fallback["内置 fallback Skill<br/>保证 demo 可移植"]
    Catalog["skill_catalog.py"]
    Manifest["Agent manifest<br/>skills: [...]"]
    Registry["Registry /skills"]
    Client["Client 选择 Agent"]

    Local --> Catalog
    Fallback --> Catalog
    Catalog --> Manifest --> Registry --> Client
```

`skill_catalog.py` 会尝试扫描本机 `~/.codex` 下的 `SKILL.md`。如果某些 Skill 不存在，就使用项目内置的 fallback 描述，所以 demo 在没有 Codex Skill 环境的机器上也能运行。

## 6. 断连与重连

```mermaid
stateDiagram-v2
    [*] --> Connected
    Connected --> Sending: write JSON-RPC
    Sending --> Waiting: wait response
    Waiting --> Connected: response ok
    Waiting --> Disconnected: EOF / timeout / BrokenPipe
    Sending --> Disconnected: BrokenPipe
    Disconnected --> Reconnecting: reconnect_count < max
    Reconnecting --> Connected: initialize ok
    Reconnecting --> Failed: retries exhausted
    Failed --> [*]
```

`reconnection_demo.py` 使用 `crash_agent.py` 模拟随机崩溃，Client 会检测 EOF、超时和 BrokenPipe，然后重新启动 Agent，并尝试恢复 session。

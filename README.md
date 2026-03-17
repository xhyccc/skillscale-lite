# 🚀 SkillScale Lite — Distributed Skill-as-a-Service Agent Infrastructure

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

✨ SkillScale Lite is a high-performance distributed infrastructure for executing AI agent skills at scale. It bridges two industry-standard agent protocols — **Model Context Protocol (MCP)** and **Google Agent-to-Agent (A2A)** — through a unified Rust gateway backed by Kafka (Redpanda), with direct skill spawning and optional OS-native sandbox isolation.

## 🧠 Core Principles

SkillScale Lite solves the **protocol fragmentation** problem in modern AI agent ecosystems. MCP clients (Claude Desktop, Cursor, etc.) and A2A agents (Google, enterprise platforms) use different protocols, while skill execution backends need a unified interface. SkillScale Lite unifies this with a three-layer architecture:

```
Protocol Layer      →  Gateway Layer      →  Execution Layer
(MCP / A2A clients)   (Rust, protocol     (Kafka + Skill Servers,
                      translation)        skill discovery & LLM)
```

- ➕ Adding a new protocol = add an HTTP handler in the Gateway
- 📂 Adding a new skill = drop a folder into `skills/` and restart
- 📈 Scaling = add more Skill Server processes (Kafka handles distribution)

## 🔄 Request Flow

```
Client ──▶ Rust Gateway ──▶ Redpanda (Kafka) ──▶ Skill Server
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 🎯 Invocation Granularity

| Granularity      | MCP Tool Name                | A2A Endpoint                                 | Routing                        |
|------------------|-----------------------------|-----------------------------------------------|-------------------------------|
| Coarse-grained   | `agent__code-analysis`       | `POST /v1/agents/code-analysis/converse`      | AGENTS.md + LLM auto-select    |
| Fine-grained     | `code-analysis__dead-code-detector` | *(not applicable)*                  | Direct skill execution         |

- 🔍 **Coarse-grained**: Caller specifies domain; Skill Server uses LLM to match best skill.
- 🎯 **Fine-grained**: Caller names the skill; Skill Server executes directly.

A2A is coarse-grained only; MCP supports both.

## 🏗️ Architecture

```
┌───────────────┐
│  Clients      │
└─────┬─────────┘
      │
┌─────▼─────┐
│ Gateway   │
└─────┬─────┘
      │
┌─────▼─────┐
│ Redpanda  │
└─────┬─────┘
      │
┌─────▼─────┐
│ Skill     │
│ Server    │
└───────────┘
```

- 🦀 **Gateway**: Rust (axum + rmcp), ports 8085 (A2A) and 8086 (MCP)
- 📨 **Redpanda**: Kafka-compatible broker, port 9092
- ⚙️ **Skill Server**: Rust + Python, consumes Kafka topic, matches skills via AGENTS.md + LLM, executes `run.py`
- 🐍 **Skills**: Python, self-contained units using `llm_utils.py`

## 🚢 Deployment

- 🖥️ **Skill servers run as native OS processes, not Docker containers**
- 🐳 Only Redpanda, Console, and Gateway run in Docker
- 🔧 Skill servers are launched natively by `run_all.sh`
- 📦 Docker Compose does not include skill-server services

## ⚡ Quick Start

### 📋 Prerequisites

| Dependency           | macOS                  | Ubuntu/Debian           |
|----------------------|-----------------------|-------------------------|
| Docker & Compose     | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust toolchain       | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | Same |
| Python >= 3.10       | `brew install python` | `apt install python3 python3-venv` |

> Docker is only needed for Redpanda (Kafka) and Gateway. Skill servers compile and run natively.

### 🚀 Launch

```bash
./run_all.sh
```

- 🐍 Creates `.venv` and installs Python dependencies
- 🦀 Compiles the skill-server Rust binary natively
- 🐳 Runs `build.sh` to launch Docker infrastructure (Redpanda + Gateway)
- ⚙️ Launches skill-server processes natively (one per category)
- ⏳ Waits for Gateway (ports 8085 + 8086) to be ready
- ✅ Runs demo scripts to validate the system

## 📁 Project Structure

```
SkillScale Lite/
├── skillscale-rs/              # Rust workspace (compiled natively)
│   ├── gateway/src/            # Axum HTTP server (A2A + MCP) — runs in Docker
│   ├── skill-server/src/       # Kafka consumer + skill executor — runs natively
│   └── common/src/             # Shared Kafka message types
├── skills/                     # Skill definitions (OpenSkills format)
│   ├── llm_utils.py            # Shared LLM client (Azure/OpenAI/Zhipu)
│   ├── code-analysis/          # Category
│   └── data-processing/        # Category
├── examples/                   # Demo scripts
├── docker/                     # Dockerfiles
├── build.sh                    # Docker build & launch
├── run_all.sh                  # Full bootstrap
└── .env                        # API keys & configuration
```

## ⚙️ Configuration

All skills share `skills/llm_utils.py`, which reads credentials from `.env`.

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| `azure`  | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_MODEL` | gpt-4o |
| `openai` | `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL` | DeepSeek-V3 |
| `zhipu`  | `ZHIPU_API_KEY`, `ZHIPU_MODEL` | GLM-4.7-FlashX |

Set `LLM_PROVIDER=azure|openai|zhipu` in `.env` to select the active provider.

## 🔗 Related Projects

After scanning this codebase and searching GitHub, the following repositories address a similar MCP ↔ A2A protocol-bridging problem and may be considered equivalent or complementary projects:

| Repository | Language | Stars | Description |
|---|---|---|---|
| [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server) | Python | ⭐ 145 | Bridges MCP with the A2A protocol so MCP-compatible assistants (e.g. Claude) can call A2A agents. *(archived)* |
| [jinyitao123/a2a-gateway](https://github.com/jinyitao123/a2a-gateway) | TypeScript | — | A2A + MCP bridge with internal bot-to-bot calls, external agent discovery, and Streamable HTTP tools. |
| [peerclaw/peerclaw-server](https://github.com/peerclaw/peerclaw-server) | Go | — | Agent registry with A2A/MCP/ACP protocol bridging, reputation engine, and access control. |
| [anatolykoptev/openclaw-a2a-bridge](https://github.com/anatolykoptev/openclaw-a2a-bridge) | JavaScript | — | A2A protocol bridge plugin — agent card, JSON-RPC endpoint, and remote agent tools. |
| [eduardpetraeus-lab/protocol-bridge](https://github.com/eduardpetraeus-lab/protocol-bridge) | — | — | Bridge between MCP and the A2A protocol. |

### 🏆 Major Advantages of SkillScale Lite

All of the projects above are **protocol adapters** — they translate between MCP and A2A but do nothing beyond that. SkillScale Lite is a **full skill-execution platform**. The table below summarises the key differences:

| Capability | SkillScale Lite | Comparable projects |
|---|---|---|
| **Distributed queue** | ✅ Kafka/Redpanda — async, durable, horizontally scalable | ❌ Direct HTTP call only |
| **Horizontal scaling** | ✅ Add more skill-server processes; Kafka distributes load automatically | ❌ Single-process or single-node |
| **LLM-powered intent routing** | ✅ Coarse-grained requests are routed to the best skill via LLM | ❌ Manual routing / fixed endpoint |
| **Pluggable skill execution** | ✅ Drop a folder into `skills/` — zero code changes to the gateway | ❌ Hard-coded agent list |
| **High-performance gateway** | ✅ Rust (axum + tokio) — low latency, low memory | ⚠️ Python / TypeScript / Go |
| **Dual invocation granularity** | ✅ Coarse (LLM routes) *and* fine (direct by name) via MCP | ❌ Coarse only |
| **Native process isolation** | ✅ Skills run as OS-native processes, not containers | ❌ Not applicable |
| **Multi-LLM provider support** | ✅ Azure OpenAI, OpenAI-compatible, Zhipu AI | ❌ Single provider |

In short, SkillScale Lite is the only project in this space that combines **protocol bridging + distributed execution + LLM-powered routing + extensible skill plugins** in a single production-ready system.

## 📄 License

MIT

---

> For other languages, see:
> - [简体中文](README_CN.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)
> - [Français](README_FR.md)

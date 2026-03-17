# 🚀 SkillScale Lite — 分布式技能即服务代理基础设施

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

✨ SkillScale Lite 是高性能分布式 AI Agent 技能执行基础设施。它通过 Rust Gateway + Kafka（Redpanda）统一支持 MCP（Model Context Protocol）和 A2A（Google Agent-to-Agent）两大协议，技能服务器原生进程启动，支持 OS 级沙箱隔离。

## 🧠 核心原理

SkillScale Lite 解决了 AI Agent 协议碎片化问题。MCP 客户端（Claude Desktop、Cursor 等）和 A2A 客户端（Google、企业平台）协议不同，技能执行后端需要统一接口。SkillScale Lite 用三层架构统一：

```
协议层      → Gateway层      → 执行层
(MCP/A2A)    (Rust协议翻译)   (Kafka + 技能服务器 + LLM)
```

- ➕ 新协议 = Gateway 增加 HTTP handler
- 📂 新技能 = skills/ 下加目录，重启即可
- 📈 扩展 = 增加技能服务器进程（Kafka 自动分发）

## 🔄 请求流转

```
客户端 ──▶ Rust Gateway ──▶ Redpanda (Kafka) ──▶ 技能服务器
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 🎯 调用粒度

| 粒度         | MCP 工具名                | A2A 端点                                 | 路由方式                |
|--------------|---------------------------|------------------------------------------|-------------------------|
| 粗粒度       | `agent__code-analysis`     | `POST /v1/agents/code-analysis/converse` | AGENTS.md + LLM自动选择 |
| 细粒度       | `code-analysis__dead-code-detector` | *(不适用)*                      | 直接执行指定技能         |

A2A 只支持粗粒度，MCP 支持两种。

## 🏗️ 架构

```
┌───────────────┐
│  客户端       │
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
│ 技能服务器 │
└───────────┘
```

- Gateway: Rust (axum + rmcp)，端口 8085 (A2A) 和 8086 (MCP)
- Redpanda: Kafka Broker，端口 9092
- 技能服务器: Rust + Python，消费 Kafka topic，AGENTS.md + LLM 匹配技能

## 🚢 部署

- 🖥️ 技能服务器以原生进程运行，不用 Docker
- 🐳 Docker 只包含 Redpanda、Console、Gateway
- 🔧 技能服务器由 run_all.sh 原生启动
- 📦 Docker Compose 不包含 skill-server 服务

## ⚡ 快速启动

### 📋 依赖

| 依赖项           | macOS                  | Ubuntu/Debian           |
|------------------|-----------------------|-------------------------|
| Docker & Compose | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust 工具链      | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | 同上 |
| Python >= 3.10   | `brew install python` | `apt install python3 python3-venv` |

> Docker 只用于 Redpanda 和 Gateway。技能服务器原生编译运行。

### 🚀 启动

```bash
./run_all.sh
```

- 🐍 创建 .venv 并安装 Python 依赖
- 🦀 编译技能服务器 Rust 二进制
- 🐳 启动 Docker（Redpanda + Gateway）
- ⚙️ 原生启动技能服务器进程（每个分类一个）
- ⏳ 等待 Gateway 就绪
- ✅ 运行 demo 脚本验证系统

## 📁 项目结构

```
SkillScale Lite/
├── skillscale-rs/              # Rust 工作区（原生编译）
│   ├── gateway/src/            # Axum HTTP 服务（A2A + MCP）— Docker
│   ├── skill-server/src/       # Kafka 消费 + 技能执行 — 原生
│   └── common/src/             # Kafka 消息类型
├── skills/                     # 技能定义
│   ├── llm_utils.py            # LLM 客户端
│   ├── code-analysis/          # 分类
│   └── data-processing/        # 分类
├── examples/                   # 演示脚本
├── docker/                     # Dockerfile
├── build.sh                    # Docker 构建与启动
├── run_all.sh                  # 全部启动
└── .env                        # API 密钥与配置
```

## ⚙️ 配置

所有技能共用 skills/llm_utils.py，读取 .env。

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

设置 LLM_PROVIDER=azure|openai|zhipu 选择模型。

## 🔗 相关项目

在扫描本代码库并检索 GitHub 后，以下仓库解决了类似的 MCP ↔ A2A 协议桥接问题，可视为等价或互补项目：

| 仓库 | 语言 | Stars | 描述 |
|---|---|---|---|
| [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server) | Python | ⭐ 145 | 将 MCP 与 A2A 协议桥接，使 Claude 等 MCP 兼容助手能调用 A2A 智能体。*(已归档)* |
| [jinyitao123/a2a-gateway](https://github.com/jinyitao123/a2a-gateway) | TypeScript | — | A2A + MCP 桥接，支持内部机器人互调、外部智能体发现和 Streamable HTTP 工具。 |
| [peerclaw/peerclaw-server](https://github.com/peerclaw/peerclaw-server) | Go | — | 支持 A2A/MCP/ACP 协议桥接的智能体注册中心，含声誉引擎和访问控制。 |
| [anatolykoptev/openclaw-a2a-bridge](https://github.com/anatolykoptev/openclaw-a2a-bridge) | JavaScript | — | A2A 协议桥接插件——智能体名片、JSON-RPC 端点和远程智能体工具。 |
| [eduardpetraeus-lab/protocol-bridge](https://github.com/eduardpetraeus-lab/protocol-bridge) | — | — | MCP 与 A2A 协议之间的桥接器。 |

### 🏆 SkillScale Lite 的核心优势

上述所有项目都是**协议适配器**——仅在 MCP 与 A2A 之间做协议转换。SkillScale Lite 是一个**完整的技能执行平台**。以下表格列出了关键差异：

| 能力 | SkillScale Lite | 同类项目 |
|---|---|---|
| **分布式队列** | ✅ Kafka/Redpanda——异步、持久化、水平可扩展 | ❌ 仅直接 HTTP 调用 |
| **水平扩展** | ✅ 增加更多 skill-server 进程；Kafka 自动分发负载 | ❌ 单进程或单节点 |
| **LLM 意图路由** | ✅ 粗粒度请求通过 LLM 自动路由到最佳技能 | ❌ 手动路由/固定端点 |
| **可插拔技能执行** | ✅ 在 `skills/` 中新建文件夹即可添加技能，无需修改网关代码 | ❌ 硬编码智能体列表 |
| **高性能网关** | ✅ Rust (axum + tokio)——低延迟、低内存占用 | ⚠️ Python / TypeScript / Go |
| **双粒度调用** | ✅ 粗粒度（LLM 路由）*和*细粒度（按名称直接调用）均支持 | ❌ 仅粗粒度 |
| **原生进程隔离** | ✅ 技能以原生 OS 进程运行，而非容器 | ❌ 不适用 |
| **多 LLM 提供商支持** | ✅ Azure OpenAI、OpenAI 兼容接口、智谱 AI | ❌ 单一提供商 |

简而言之，SkillScale Lite 是该领域唯一将**协议桥接 + 分布式执行 + LLM 智能路由 + 可扩展技能插件**融为一体的生产就绪系统。

## 📄 License

MIT

---

> 其他语言：
> - [English](README.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)
> - [Français](README_FR.md)
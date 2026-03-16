# SkillScale Lite — 分布式技能即服务代理基础设施

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

SkillScale Lite 是高性能分布式 AI Agent 技能执行基础设施。它通过 Rust Gateway + Kafka（Redpanda）统一支持 MCP（Model Context Protocol）和 A2A（Google Agent-to-Agent）两大协议，技能服务器原生进程启动，支持 OS 级沙箱隔离。

## 核心原理

SkillScale Lite 解决了 AI Agent 协议碎片化问题。MCP 客户端（Claude Desktop、Cursor 等）和 A2A 客户端（Google、企业平台）协议不同，技能执行后端需要统一接口。SkillScale Lite 用三层架构统一：

```
协议层      → Gateway层      → 执行层
(MCP/A2A)    (Rust协议翻译)   (Kafka + 技能服务器 + LLM)
```

- 新协议 = Gateway 增加 HTTP handler
- 新技能 = skills/ 下加目录，重启即可
- 扩展 = 增加技能服务器进程（Kafka 自动分发）

## 请求流转

```
客户端 ──▶ Rust Gateway ──▶ Redpanda (Kafka) ──▶ 技能服务器
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 调用粒度

| 粒度         | MCP 工具名                | A2A 端点                                 | 路由方式                |
|--------------|---------------------------|------------------------------------------|-------------------------|
| 粗粒度       | `agent__code-analysis`     | `POST /v1/agents/code-analysis/converse` | AGENTS.md + LLM自动选择 |
| 细粒度       | `code-analysis__dead-code-detector` | *(不适用)*                      | 直接执行指定技能         |

A2A 只支持粗粒度，MCP 支持两种。

## 架构

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

## 部署

- 技能服务器以原生进程运行，不用 Docker
- Docker 只包含 Redpanda、Console、Gateway
- 技能服务器由 run_all.sh 原生启动
- Docker Compose 不包含 skill-server 服务

## 快速启动

### 依赖

| 依赖项           | macOS                  | Ubuntu/Debian           |
|------------------|-----------------------|-------------------------|
| Docker & Compose | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust 工具链      | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | 同上 |
| Python >= 3.10   | `brew install python` | `apt install python3 python3-venv` |

> Docker 只用于 Redpanda 和 Gateway。技能服务器原生编译运行。

### 启动

```bash
./run_all.sh
```

- 创建 .venv 并安装 Python 依赖
- 编译技能服务器 Rust 二进制
- 启动 Docker（Redpanda + Gateway）
- 原生启动技能服务器进程（每个分类一个）
- 等待 Gateway 就绪
- 运行 demo 脚本验证系统

## 项目结构

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

## 配置

所有技能共用 skills/llm_utils.py，读取 .env。

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

设置 LLM_PROVIDER=azure|openai|zhipu 选择模型。

## License

MIT

---

> 其他语言：
> - [English](README.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)
> - [Français](README_FR.md)
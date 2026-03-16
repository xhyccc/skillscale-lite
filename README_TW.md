# SkillScale Lite — 分散式技能即服務代理基礎設施

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

SkillScale Lite 是高效能分散式 AI Agent 技能執行基礎設施。透過 Rust Gateway + Kafka（Redpanda）統一支援 MCP（Model Context Protocol）和 A2A（Google Agent-to-Agent）兩大協議，技能伺服器原生進程啟動，支援 OS 級沙箱隔離。

## 核心原理

SkillScale Lite 解決 AI Agent 協議碎片化問題。MCP 客戶端（Claude Desktop、Cursor 等）和 A2A 客戶端（Google、企業平台）協議不同，技能執行後端需要統一介面。SkillScale Lite 用三層架構統一：

```
協議層      → Gateway層      → 執行層
(MCP/A2A)    (Rust協議翻譯)   (Kafka + 技能伺服器 + LLM)
```

- 新協議 = Gateway 增加 HTTP handler
- 新技能 = skills/ 下加目錄，重啟即可
- 擴展 = 增加技能伺服器進程（Kafka 自動分發）

## 請求流轉

```
客戶端 ──▶ Rust Gateway ──▶ Redpanda (Kafka) ──▶ 技能伺服器
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 呼叫粒度

| 粒度         | MCP 工具名                | A2A 端點                                 | 路由方式                |
|--------------|---------------------------|------------------------------------------|-------------------------|
| 粗粒度       | `agent__code-analysis`     | `POST /v1/agents/code-analysis/converse` | AGENTS.md + LLM自動選擇 |
| 細粒度       | `code-analysis__dead-code-detector` | *(不適用)*                      | 直接執行指定技能         |

A2A 只支援粗粒度，MCP 支援兩種。

## 架構

```
┌───────────────┐
│  客戶端       │
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
│ 技能伺服器 │
└───────────┘
```

- Gateway: Rust (axum + rmcp)，端口 8085 (A2A) 和 8086 (MCP)
- Redpanda: Kafka Broker，端口 9092
- 技能伺服器: Rust + Python，消費 Kafka topic，AGENTS.md + LLM 匹配技能

## 部署

- 技能伺服器以原生進程運行，不用 Docker
- Docker 只包含 Redpanda、Console、Gateway
- 技能伺服器由 run_all.sh 原生啟動
- Docker Compose 不包含 skill-server 服務

## 快速啟動

### 依賴

| 依賴項           | macOS                  | Ubuntu/Debian           |
|------------------|-----------------------|-------------------------|
| Docker & Compose | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust 工具鏈      | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | 同上 |
| Python >= 3.10   | `brew install python` | `apt install python3 python3-venv` |

> Docker 只用於 Redpanda 和 Gateway。技能伺服器原生編譯運行。

### 啟動

```bash
./run_all.sh
```

- 建立 .venv 並安裝 Python 依賴
- 編譯技能伺服器 Rust 二進制
- 啟動 Docker（Redpanda + Gateway）
- 原生啟動技能伺服器進程（每個分類一個）
- 等待 Gateway 就緒
- 執行 demo 腳本驗證系統

## 專案結構

```
SkillScale Lite/
├── skillscale-rs/              # Rust 工作區（原生編譯）
│   ├── gateway/src/            # Axum HTTP 服務（A2A + MCP）— Docker
│   ├── skill-server/src/       # Kafka 消費 + 技能執行 — 原生
│   └── common/src/             # Kafka 訊息型別
├── skills/                     # 技能定義
│   ├── llm_utils.py            # LLM 客戶端
│   ├── code-analysis/          # 分類
│   └── data-processing/        # 分類
├── examples/                   # 演示腳本
├── docker/                     # Dockerfile
├── build.sh                    # Docker 建構與啟動
├── run_all.sh                  # 全部啟動
└── .env                        # API 金鑰與配置
```

## 配置

所有技能共用 skills/llm_utils.py，讀取 .env。

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

設定 LLM_PROVIDER=azure|openai|zhipu 選擇模型。

## License

MIT

---

> 其他語言：
> - [English](README.md)
> - [简体中文](README_CN.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)
> - [Français](README_FR.md)

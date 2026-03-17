# 🚀 SkillScale Lite — 分散型スキル・アズ・サービス エージェント基盤

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

✨ SkillScale Lite は高性能分散型 AI Agent スキル実行基盤です。Rust Gateway + Kafka（Redpanda）で MCP（Model Context Protocol）と A2A（Google Agent-to-Agent）両方のプロトコルを統一し、スキルサーバはネイティブプロセスで起動、OSレベルのサンドボックスもサポート。

## 🧠 コア原則

SkillScale Lite は AI Agent のプロトコル断片化問題を解決します。MCP クライアント（Claude Desktop、Cursor 等）と A2A クライアント（Google、企業プラットフォーム）はプロトコルが異なり、スキル実行バックエンドは統一インターフェースが必要です。SkillScale Lite は三層アーキテクチャで統一：

```
プロトコル層 → Gateway層 → 実行層
(MCP/A2A)     (Rustプロトコル変換) (Kafka + スキルサーバ + LLM)
```

- ➕ 新プロトコル = Gateway に HTTP handler 追加
- 📂 新スキル = skills/ にディレクトリ追加、再起動
- 📈 拡張 = スキルサーバプロセス追加（Kafka 自動分散）

## 🔄 リクエストフロー

```
クライアント ──▶ Rust Gateway ──▶ Redpanda (Kafka) ──▶ スキルサーバ
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 🎯 呼び出し粒度

| 粒度         | MCP ツール名                | A2A エンドポイント                        | ルーティング                |
|--------------|-----------------------------|--------------------------------------------|----------------------------|
| 粗粒度       | `agent__code-analysis`       | `POST /v1/agents/code-analysis/converse`   | AGENTS.md + LLM自動選択    |
| 細粒度       | `code-analysis__dead-code-detector` | *(該当なし)*                        | 指定スキル直接実行         |

A2A は粗粒度のみ、MCP は両方対応。

## 🏗️ アーキテクチャ

```
┌───────────────┐
│  クライアント │
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
│ スキルサーバ │
└───────────┘
```

- Gateway: Rust (axum + rmcp)、ポート 8085 (A2A)・8086 (MCP)
- Redpanda: Kafka Broker、ポート 9092
- スキルサーバ: Rust + Python、Kafka topic 消費、AGENTS.md + LLM でスキル選択

## 🚢 デプロイ

- 🖥️ スキルサーバはネイティブプロセスで実行、Docker不要
- 🐳 Docker には Redpanda・Console・Gateway のみ
- 🔧 スキルサーバは run_all.sh でネイティブ起動
- 📦 Docker Compose に skill-server サービスなし

## ⚡ クイックスタート

### 📋 依存

| 依存項目           | macOS                  | Ubuntu/Debian           |
|--------------------|-----------------------|-------------------------|
| Docker & Compose   | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust ツールチェーン | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | 同上 |
| Python >= 3.10     | `brew install python` | `apt install python3 python3-venv` |

> Docker は Redpanda・Gateway のみ。スキルサーバはネイティブでビルド・実行。

### 🚀 起動

```bash
./run_all.sh
```

- 🐍 .venv 作成 & Python 依存インストール
- 🦀 スキルサーバ Rust バイナリビルド
- 🐳 Docker 起動（Redpanda + Gateway）
- ⚙️ ネイティブでスキルサーバ起動（各カテゴリごと）
- ⏳ Gateway 待機
- ✅ demo スクリプトで検証

## 📁 プロジェクト構成

```
SkillScale Lite/
├── skillscale-rs/              # Rust ワークスペース（ネイティブビルド）
│   ├── gateway/src/            # Axum HTTP サーバ（A2A + MCP）— Docker
│   ├── skill-server/src/       # Kafka 消費 + スキル実行 — ネイティブ
│   └── common/src/             # Kafka メッセージ型
├── skills/                     # スキル定義
│   ├── llm_utils.py            # LLM クライアント
│   ├── code-analysis/          # カテゴリ
│   └── data-processing/        # カテゴリ
├── examples/                   # デモスクリプト
├── docker/                     # Dockerfile
├── build.sh                    # Docker ビルド・起動
├── run_all.sh                  # 全体起動
└── .env                        # APIキー・設定
```

## ⚙️ 設定

全スキル共通で skills/llm_utils.py を利用し .env を読み込み。

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

LLM_PROVIDER=azure|openai|zhipu で選択。

## 🔗 関連プロジェクト

このコードベースをスキャンし GitHub を検索した結果、以下のリポジトリが同様の MCP ↔ A2A プロトコルブリッジ問題を解決しており、同等または補完的なプロジェクトとして挙げられます：

| リポジトリ | 言語 | Stars | 説明 |
|---|---|---|---|
| [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server) | Python | ⭐ 145 | MCP と A2A プロトコルを橋渡しし、Claude などの MCP 対応アシスタントが A2A エージェントを呼び出せるようにする。*(アーカイブ済み)* |
| [jinyitao123/a2a-gateway](https://github.com/jinyitao123/a2a-gateway) | TypeScript | — | A2A + MCP ブリッジ。内部ボット間通信、外部エージェント検出、Streamable HTTP ツールをサポート。 |
| [peerclaw/peerclaw-server](https://github.com/peerclaw/peerclaw-server) | Go | — | A2A/MCP/ACP プロトコルブリッジを備えたエージェントレジストリ。レピュテーションエンジンとアクセス制御付き。 |
| [anatolykoptev/openclaw-a2a-bridge](https://github.com/anatolykoptev/openclaw-a2a-bridge) | JavaScript | — | A2A プロトコルブリッジプラグイン——エージェントカード、JSON-RPC エンドポイント、リモートエージェントツール。 |
| [eduardpetraeus-lab/protocol-bridge](https://github.com/eduardpetraeus-lab/protocol-bridge) | — | — | MCP と A2A プロトコルのブリッジ。 |

### 🏆 SkillScale Lite の主な優位点

上記のプロジェクトはすべて**プロトコルアダプタ**です——MCP と A2A 間のプロトコル変換しか行いません。SkillScale Lite は**完全なスキル実行プラットフォーム**です。以下の表に主な違いをまとめます：

| 機能 | SkillScale Lite | 同等プロジェクト |
|---|---|---|
| **分散キュー** | ✅ Kafka/Redpanda——非同期・永続化・水平スケール可能 | ❌ 直接 HTTP 呼び出しのみ |
| **水平スケーリング** | ✅ skill-server プロセスを追加するだけ；Kafka が自動で負荷分散 | ❌ 単一プロセス/単一ノード |
| **LLM 意図ルーティング** | ✅ 粗粒度リクエストを LLM が最適なスキルへ自動ルーティング | ❌ 手動ルーティング/固定エンドポイント |
| **プラガブルスキル実行** | ✅ `skills/` にフォルダを追加するだけ——ゲートウェイ変更不要 | ❌ エージェントリストがハードコード |
| **高性能ゲートウェイ** | ✅ Rust (axum + tokio)——低レイテンシ・低メモリ | ⚠️ Python / TypeScript / Go |
| **二段階呼び出し粒度** | ✅ 粗粒度（LLM ルーティング）*と*細粒度（名前で直接指定）の両方 | ❌ 粗粒度のみ |
| **ネイティブプロセス分離** | ✅ スキルはコンテナでなくネイティブ OS プロセスとして実行 | ❌ 該当なし |
| **マルチ LLM プロバイダ** | ✅ Azure OpenAI、OpenAI 互換、Zhipu AI | ❌ 単一プロバイダ |

一言で言えば、SkillScale Lite は**プロトコルブリッジ + 分散実行 + LLM ルーティング + 拡張可能スキルプラグイン**をすべて兼ね備えた、この分野唯一のプロダクション対応システムです。

## 📄 License

MIT

---

> 他言語：
> - [English](README.md)
> - [简体中文](README_CN.md)
> - [繁體中文](README_TW.md)
> - [Español](README_ES.md)
> - [Français](README_FR.md)

# 🚀 SkillScale Lite — Infrastructure distribuée d'agent « Skill-as-a-Service »

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

✨ SkillScale Lite est une infrastructure distribuée haute performance pour exécuter des compétences d'agents IA à grande échelle. Elle unifie les protocoles MCP (Model Context Protocol) et A2A (Google Agent-to-Agent) via une passerelle Rust et Kafka (Redpanda), avec serveurs de compétences natifs et isolation sandbox OS optionnelle.

## 🧠 Principes fondamentaux

SkillScale Lite résout le problème de fragmentation des protocoles dans les écosystèmes d'agents IA. Les clients MCP (Claude Desktop, Cursor, etc.) et les agents A2A (Google, plateformes d'entreprise) utilisent des protocoles différents, tandis que les backends d'exécution nécessitent une interface unifiée. SkillScale Lite unifie cela avec une architecture à trois couches :

```
Couche protocole → Couche passerelle → Couche exécution
(MCP/A2A)        (Rust, traduction)   (Kafka + serveurs de compétences + LLM)
```

- ➕ Nouveau protocole = ajouter un handler HTTP dans la passerelle
- 📂 Nouvelle compétence = ajouter un dossier dans skills/ et redémarrer
- 📈 Scalabilité = ajouter des processus serveurs de compétences (Kafka distribue)

## 🔄 Flux de requête

```
Client ──▶ Passerelle Rust ──▶ Redpanda (Kafka) ──▶ Serveur de compétences
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## 🎯 Granularité d'appel

| Granularité   | Nom outil MCP                | Endpoint A2A                              | Routage                        |
|--------------|------------------------------|--------------------------------------------|-------------------------------|
| Grossière    | `agent__code-analysis`        | `POST /v1/agents/code-analysis/converse`   | AGENTS.md + LLM auto-sélection |
| Fine         | `code-analysis__dead-code-detector` | *(non applicable)*                  | Exécution directe de compétence|

A2A ne supporte que la granularité grossière ; MCP les deux.

## 🏗️ Architecture

```
┌───────────────┐
│  Client       │
└─────┬─────────┘
      │
┌─────▼─────┐
│ Passerelle│
└─────┬─────┘
      │
┌─────▼─────┐
│ Redpanda  │
└─────┬─────┘
      │
┌─────▼─────┐
│ Serveur   │
│ de comp.  │
└───────────┘
```

- Passerelle : Rust (axum + rmcp), ports 8085 (A2A) et 8086 (MCP)
- Redpanda : Broker Kafka, port 9092
- Serveur de compétences : Rust + Python, consomme topic Kafka, AGENTS.md + LLM pour sélection

## 🚢 Déploiement

- 🖥️ Les serveurs de compétences s'exécutent comme processus natifs, pas en Docker
- 🐳 Docker inclut seulement Redpanda, Console et Passerelle
- 🔧 Les serveurs de compétences sont lancés nativement via run_all.sh
- 📦 Docker Compose n'inclut pas de services skill-server

## ⚡ Démarrage rapide

### 📋 Prérequis

| Dépendance         | macOS                  | Ubuntu/Debian           |
|--------------------|-----------------------|-------------------------|
| Docker & Compose   | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust toolchain     | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | Idem |
| Python >= 3.10     | `brew install python` | `apt install python3 python3-venv` |

> Docker est seulement nécessaire pour Redpanda et Passerelle. Les serveurs de compétences compilent et s'exécutent nativement.

### 🚀 Lancement

```bash
./run_all.sh
```

- 🐍 Crée .venv et installe dépendances Python
- 🦀 Compile le binaire Rust du serveur de compétences
- 🐳 Lance Docker (Redpanda + Passerelle)
- ⚙️ Lance processus natifs de serveur de compétences (un par catégorie)
- ⏳ Attend Passerelle
- ✅ Exécute scripts demo pour valider

## 📁 Structure du projet

```
SkillScale Lite/
├── skillscale-rs/              # Workspace Rust (compilé nativement)
│   ├── gateway/src/            # Serveur HTTP Axum (A2A + MCP) — Docker
│   ├── skill-server/src/       # Consommateur Kafka + exécuteur de compétences — natif
│   └── common/src/             # Types de message Kafka
├── skills/                     # Définitions de compétences
│   ├── llm_utils.py            # Client LLM
│   ├── code-analysis/          # Catégorie
│   └── data-processing/        # Catégorie
├── examples/                   # Scripts demo
├── docker/                     # Dockerfile
├── build.sh                    # Build et lancement Docker
├── run_all.sh                  # Lancement complet
└── .env                        # Clés API et configuration
```

## ⚙️ Configuration

Toutes les compétences utilisent skills/llm_utils.py, qui lit .env.

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

LLM_PROVIDER=azure|openai|zhipu pour sélectionner.

## 📄 License

MIT

---

> Autres langues :
> - [English](README.md)
> - [简体中文](README_CN.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)

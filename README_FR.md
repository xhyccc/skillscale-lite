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

## 🔗 Projets Connexes

Après avoir analysé ce dépôt et recherché sur GitHub, les dépôts suivants traitent un problème similaire de pont de protocole MCP ↔ A2A et peuvent être considérés comme des projets équivalents ou complémentaires :

| Dépôt | Langage | Stars | Description |
|---|---|---|---|
| [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server) | Python | ⭐ 145 | Connecte MCP au protocole A2A pour que les assistants compatibles MCP (ex. Claude) puissent appeler des agents A2A. *(archivé)* |
| [jinyitao123/a2a-gateway](https://github.com/jinyitao123/a2a-gateway) | TypeScript | — | Pont A2A + MCP avec appels internes entre bots, découverte externe d'agents et outils Streamable HTTP. |
| [peerclaw/peerclaw-server](https://github.com/peerclaw/peerclaw-server) | Go | — | Registre d'agents avec pont de protocoles A2A/MCP/ACP, moteur de réputation et contrôle d'accès. |
| [anatolykoptev/openclaw-a2a-bridge](https://github.com/anatolykoptev/openclaw-a2a-bridge) | JavaScript | — | Plugin de pont du protocole A2A — carte d'agent, point de terminaison JSON-RPC et outils d'agent distant. |
| [eduardpetraeus-lab/protocol-bridge](https://github.com/eduardpetraeus-lab/protocol-bridge) | — | — | Pont entre MCP et le protocole A2A. |

### 🏆 Principaux Avantages de SkillScale Lite

Tous les projets ci-dessus sont des **adaptateurs de protocole** — ils se contentent de traduire entre MCP et A2A. SkillScale Lite est une **plateforme d'exécution de compétences complète**. Le tableau suivant résume les différences clés :

| Capacité | SkillScale Lite | Projets comparables |
|---|---|---|
| **File d'attente distribuée** | ✅ Kafka/Redpanda — asynchrone, persistant, scalable horizontalement | ❌ Appel HTTP direct uniquement |
| **Mise à l'échelle horizontale** | ✅ Ajouter des processus skill-server ; Kafka distribue la charge automatiquement | ❌ Processus unique / nœud unique |
| **Routage d'intention par LLM** | ✅ Les requêtes grossières sont routées vers la meilleure compétence par LLM | ❌ Routage manuel / endpoint fixe |
| **Exécution de compétences enfichable** | ✅ Ajouter un dossier dans `skills/` — aucune modification du gateway | ❌ Liste d'agents codée en dur |
| **Gateway haute performance** | ✅ Rust (axum + tokio) — faible latence, faible mémoire | ⚠️ Python / TypeScript / Go |
| **Double granularité d'invocation** | ✅ Grossière (LLM route) *et* fine (directe par nom) via MCP | ❌ Grossière uniquement |
| **Isolation de processus natif** | ✅ Les compétences s'exécutent en tant que processus OS natifs, pas des conteneurs | ❌ Non applicable |
| **Support multi-fournisseur LLM** | ✅ Azure OpenAI, compatible OpenAI, Zhipu AI | ❌ Fournisseur unique |

En résumé, SkillScale Lite est le seul projet dans cet espace qui combine **pont de protocole + exécution distribuée + routage LLM + plugins de compétences extensibles** dans un seul système prêt pour la production.

## 📄 License

MIT

---

> Autres langues :
> - [English](README.md)
> - [简体中文](README_CN.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Español](README_ES.md)

# SkillScale Lite — Infraestructura distribuida de habilidades como servicio para agentes

> [English](README.md) | [简体中文](README_CN.md) | [繁體中文](README_TW.md) | [日本語](README_JP.md) | [Español](README_ES.md) | [Français](README_FR.md)

---

SkillScale Lite es una infraestructura distribuida de alto rendimiento para ejecutar habilidades de agentes de IA a escala. Unifica los protocolos MCP (Model Context Protocol) y A2A (Google Agent-to-Agent) mediante un gateway Rust y Kafka (Redpanda), con servidores de habilidades nativos y aislamiento opcional por sandbox del sistema operativo.

## Principios fundamentales

SkillScale Lite resuelve el problema de fragmentación de protocolos en ecosistemas de agentes de IA. Los clientes MCP (Claude Desktop, Cursor, etc.) y los agentes A2A (Google, plataformas empresariales) usan protocolos distintos, mientras que los backends de ejecución requieren una interfaz unificada. SkillScale Lite lo unifica con una arquitectura de tres capas:

```
Capa de protocolo → Capa de gateway → Capa de ejecución
(MCP/A2A)         (Rust, traducción) (Kafka + servidores de habilidades + LLM)
```

- Nuevo protocolo = añadir handler HTTP en el gateway
- Nueva habilidad = añadir carpeta en skills/ y reiniciar
- Escalado = añadir procesos de servidor de habilidades (Kafka distribuye)

## Flujo de solicitud

```
Cliente ──▶ Gateway Rust ──▶ Redpanda (Kafka) ──▶ Servidor de habilidades
                                            │
                                            ├── parse AGENTS.md
                                            ├── LLM intent match (coarse)
                                            │   or direct execution (fine)
                                            ├── execute scripts/run.py
                                            └── return result → Kafka → Gateway → Client
```

## Granularidad de invocación

| Granularidad   | Nombre herramienta MCP         | Endpoint A2A                              | Enrutamiento                  |
|---------------|-------------------------------|--------------------------------------------|-------------------------------|
| Gruesa        | `agent__code-analysis`         | `POST /v1/agents/code-analysis/converse`   | AGENTS.md + LLM auto-selección|
| Fina          | `code-analysis__dead-code-detector` | *(no aplica)*                        | Ejecución directa de habilidad|

A2A solo soporta granularidad gruesa; MCP ambas.

## Arquitectura

```
┌───────────────┐
│  Cliente      │
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
│ Servidor  │
│ de hab.   │
└───────────┘
```

- Gateway: Rust (axum + rmcp), puertos 8085 (A2A) y 8086 (MCP)
- Redpanda: Broker Kafka, puerto 9092
- Servidor de habilidades: Rust + Python, consume topic Kafka, AGENTS.md + LLM para selección

## Despliegue

- Los servidores de habilidades se ejecutan como procesos nativos, no en Docker
- Docker solo incluye Redpanda, Console y Gateway
- Los servidores de habilidades se lanzan nativamente con run_all.sh
- Docker Compose no incluye servicios skill-server

## Inicio rápido

### Requisitos

| Dependencia         | macOS                  | Ubuntu/Debian           |
|---------------------|-----------------------|-------------------------|
| Docker & Compose    | `brew install docker` | `apt install docker.io docker-compose-plugin` |
| Rust toolchain      | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` | Igual |
| Python >= 3.10      | `brew install python` | `apt install python3 python3-venv` |

> Docker solo es necesario para Redpanda y Gateway. Los servidores de habilidades se compilan y ejecutan nativamente.

### Lanzamiento

```bash
./run_all.sh
```

- Crea .venv e instala dependencias Python
- Compila el binario Rust del servidor de habilidades
- Lanza Docker (Redpanda + Gateway)
- Lanza procesos nativos de servidor de habilidades (uno por categoría)
- Espera Gateway
- Ejecuta scripts demo para validar

## Estructura del proyecto

```
SkillScale Lite/
├── skillscale-rs/              # Workspace Rust (compilado nativo)
│   ├── gateway/src/            # Servidor HTTP Axum (A2A + MCP) — Docker
│   ├── skill-server/src/       # Consumidor Kafka + ejecutor de habilidades — nativo
│   └── common/src/             # Tipos de mensaje Kafka
├── skills/                     # Definiciones de habilidades
│   ├── llm_utils.py            # Cliente LLM
│   ├── code-analysis/          # Categoría
│   └── data-processing/        # Categoría
├── examples/                   # Scripts demo
├── docker/                     # Dockerfile
├── build.sh                    # Build y lanzamiento Docker
├── run_all.sh                  # Lanzamiento completo
└── .env                        # Claves API y configuración
```

## Configuración

Todas las habilidades usan skills/llm_utils.py, que lee .env.

| Provider | Env Vars | Example Model |
|----------|----------|---------------|
| azure    | AZURE_API_KEY, AZURE_API_BASE, AZURE_MODEL | gpt-4o |
| openai   | OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL | DeepSeek-V3 |
| zhipu    | ZHIPU_API_KEY, ZHIPU_MODEL | GLM-4.7-FlashX |

LLM_PROVIDER=azure|openai|zhipu para seleccionar.

## License

MIT

---

> Otros idiomas:
> - [English](README.md)
> - [简体中文](README_CN.md)
> - [繁體中文](README_TW.md)
> - [日本語](README_JP.md)
> - [Français](README_FR.md)

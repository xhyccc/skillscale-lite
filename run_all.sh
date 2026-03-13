#!/usr/bin/env bash
#
# run_all.sh — Bootstrap and Launch SkillScale Lite System
#
# Architecture:
#   Docker:  Redpanda (Kafka) + Console + Gateway
#   Native:  Skill Servers (Rust binary, direct spawn / skilllite-sandbox)
#
# This script:
#   1. Sets up the Python environment
#   2. Compiles the Rust skill-server binary natively
#   3. Invokes build.sh to launch Docker infrastructure (Redpanda + Gateway)
#   4. Launches skill-server processes natively (one per category)
#   5. Waits for services to be ready
#   6. Validates endpoints (A2A + MCP)
#
set -euo pipefail
cd "$(dirname "$0")"

echo "=========================================="
echo "    Launching SkillScale Lite System      "
echo "    Docker:  Redpanda + Gateway           "
echo "    Native:  Skill Servers (direct spawn) "
echo "=========================================="

# ── Cleanup function to kill native skill-servers on exit ──
SKILL_SERVER_PIDS=()
cleanup() {
    echo ""
    echo "[cleanup] Stopping native skill-server processes..."
    for pid in "${SKILL_SERVER_PIDS[@]}"; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            echo "  Stopped skill-server PID $pid"
        fi
    done
    # Optionally stop Docker services too
    # docker compose down 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# 1. Setup Python Virtual Environment
echo ""
echo "[1] Setting up Python dependencies..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -r requirements.txt >/dev/null
export PYTHONPATH="${PYTHONPATH:-}:."

# 2. Compile Rust skill-server binary (native)
echo ""
echo "[2] Compiling skill-server binary (native)..."
if ! command -v cargo &>/dev/null; then
    echo "ERROR: Rust/cargo not found. Install from https://rustup.rs/"
    exit 1
fi
(cd skillscale-rs && cargo build --release -p skill-server 2>&1)
SKILL_SERVER_BIN="$(pwd)/skillscale-rs/target/release/skill-server"
if [[ ! -x "$SKILL_SERVER_BIN" ]]; then
    echo "ERROR: skill-server binary not found at $SKILL_SERVER_BIN"
    exit 1
fi
echo "  skill-server binary: $SKILL_SERVER_BIN"

# 3. Build and Start Docker Infrastructure (Redpanda + Gateway)
echo ""
echo "[3] Starting Docker infrastructure via build.sh..."
# Purge Kafka/Redpanda volumes to avoid stale messages from previous runs
docker compose down -v 2>/dev/null || true
# Pass arguments like --no-clean to build.sh if provided
bash build.sh "$@"

# Wait for Rust Gateway (A2A on 8085, MCP on 8086)
echo "Waiting for Rust Gateway..."
for ((i=1; i<=30; i++)); do
    if curl -s http://localhost:8085/health >/dev/null 2>&1; then
        echo "  A2A port 8085 is ready."
        break
    fi
    echo -n "."
    sleep 2
done
for ((i=1; i<=15; i++)); do
    if python3 -c "import socket; s = socket.socket(); s.settimeout(1); s.connect(('localhost', 8086))" 2>/dev/null; then
        echo "  MCP port 8086 is ready."
        break
    fi
    sleep 1
done
echo ""

# 4. Launch native skill-server processes (one per category)
echo "[4] Launching native skill-server processes..."

# Load .env to get LLM credentials
set -a
source .env
set +a

# Discover skill categories
for dir in skills/*/; do
    dirname=$(basename "$dir")
    [[ "$dirname" == "__pycache__" ]] && continue
    [[ ! -f "$dir/AGENTS.md" ]] && continue

    topic="TOPIC_$(echo "$dirname" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
    group_id="skill-server-group-${dirname}"
    log_file="/tmp/skill-server-${dirname}.log"

    echo "  Starting skill-server for '$dirname' (topic=$topic)..."

    # Launch skill-server as background process
    SKILLSCALE_TOPIC="$topic" \
    SKILLSCALE_GROUP_ID="$group_id" \
    SKILLSCALE_BROKER_URL="localhost:9092" \
    SKILLSCALE_ROOT="$(pwd)" \
    SKILLSCALE_SANDBOX="${SKILLSCALE_SANDBOX:-none}" \
    RUST_LOG="${RUST_LOG:-info,skill_server=debug}" \
    "$SKILL_SERVER_BIN" > "$log_file" 2>&1 &

    pid=$!
    SKILL_SERVER_PIDS+=("$pid")
    echo "  skill-server '$dirname' started (PID=$pid, log=$log_file)"
done

# Wait a moment for skill servers to start and discover skills
sleep 2

# Verify skill servers are running
echo ""
echo "  Skill server status:"
all_ok=true
for pid in "${SKILL_SERVER_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
        echo "    PID $pid: running ✓"
    else
        echo "    PID $pid: FAILED ✗"
        all_ok=false
    fi
done
if ! $all_ok; then
    echo "  WARNING: Some skill servers failed to start. Check /tmp/skill-server-*.log"
fi

# 5. Validation
echo ""
echo "[5] Validating SkillScale Lite Gateway..."

# 5.1 Verify A2A Protocol (HTTP)
echo "- Validating A2A Client Demo (HTTP)..."
if python3 examples/demo_a2a_client.py; then
    echo "  ✓ A2A Client Demo Passed"
else
    echo "  ✗ A2A Client Demo Failed (Check docker logs gateway / /tmp/skill-server-*.log)"
    exit 1
fi

echo ""
# 5.2 Verify MCP Protocol (Streamable HTTP)
echo "- Validating MCP Client Demo (http://localhost:8086/mcp)..."
if python3 examples/demo_mcp_client.py; then
    echo "  ✓ MCP Client Demo Passed"
else
    echo "  ✗ MCP Client Demo Failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "    SkillScale Lite System Ready!         "
echo "=========================================="
echo "  Docker services:"
echo "  • Redpanda Kafka:   localhost:9092"
echo "  • Console (Web):    http://localhost:8080"
echo "  • A2A Gateway:      http://localhost:8085"
echo "  • MCP Server:       http://localhost:8086/mcp"
echo ""
echo "  Native skill-servers:"
for pid in "${SKILL_SERVER_PIDS[@]}"; do
    echo "    • PID $pid"
done
echo ""
echo "  Logs:  /tmp/skill-server-*.log"
echo "  Stop:  Ctrl+C (or kill PIDs above)"
echo "=========================================="

# Keep running until Ctrl+C (skill-servers are background processes)
echo ""
echo "Press Ctrl+C to stop all services..."
wait


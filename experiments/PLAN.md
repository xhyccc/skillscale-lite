# Experiment Plan: SkillScale Lite Evaluation

This document describes the complete experiment plan for evaluating SkillScale Lite against comparable systems, including the list of repositories used as baselines, the metrics collected, and the step-by-step methodology.

---

## 1. Comparable Repositories

The following open-source projects represent the state of the art in MCP/A2A protocol bridging and are used as comparison points.  All are publicly available on GitHub.

| # | Repository | Language | Description |
|---|-----------|----------|-------------|
| B1 | [GongRzhe/A2A-MCP-Server](https://github.com/GongRzhe/A2A-MCP-Server) | Python | MCP→A2A adapter; direct HTTP translation, no queue (archived) |
| B2 | [jinyitao123/a2a-gateway](https://github.com/jinyitao123/a2a-gateway) | TypeScript | A2A + MCP bridge with bot-to-bot calls, synchronous HTTP backend |
| B3 | [peerclaw/peerclaw-server](https://github.com/peerclaw/peerclaw-server) | Go | Agent registry with A2A/MCP/ACP bridging, static routing |
| B4 | [anatolykoptev/openclaw-a2a-bridge](https://github.com/anatolykoptev/openclaw-a2a-bridge) | JavaScript | A2A bridge plugin; agent card + JSON-RPC endpoint |
| B5 | [eduardpetraeus-lab/protocol-bridge](https://github.com/eduardpetraeus-lab/protocol-bridge) | — | Thin MCP↔A2A bridge, no execution infrastructure |

SkillScale Lite is also compared against two architectural baselines derived from the above pattern:

| # | Baseline | Represents |
|---|----------|-----------|
| C1 | **Docker baseline** | Container-per-invocation isolation (pre-existing `arch.md` design) |
| C2 | **Direct-HTTP baseline** | Synchronous HTTP skill execution without a message broker (pattern of B1–B5) |

---

## 2. Feature Comparison Methodology

### Goal
Produce Table 1 in the paper: a binary/ternary feature matrix comparing SkillScale Lite against B1–B4 across 12 capability dimensions.

### Features Assessed
1. MCP support
2. A2A support
3. Distributed message queue
4. Horizontal worker scaling
5. LLM-powered intent routing
6. Pluggable skill execution
7. High-performance gateway (Rust)
8. Dual invocation granularity (coarse + fine)
9. Native OS process isolation
10. Multi-LLM provider support
11. Agent registry / discovery
12. Access control / reputation engine

### Assessment Protocol
For each repository B1–B5, the assessor must:
1. Clone the repository at the latest tagged release (or `HEAD` if no release exists).
2. Read the README, architecture docs, and source code.
3. Attempt to invoke a skill (or equivalent capability) through both MCP and A2A.
4. Mark each feature as: ✓ (present and functional), ~ (partially present), or ✗ (absent).
5. Record the commit SHA and assessment date for reproducibility.

---

## 3. Performance Experiments

### 3.1 Hardware Configuration

All measurements must be taken on a single machine with a documented specification.  The reference configuration used in the paper is:

- **Machine**: Apple M2 Pro, 16 GB RAM, macOS 14.5
- **Docker**: Docker Desktop 4.30
- **Redpanda**: version 23.3
- **Rust toolchain**: `cargo build --release` (stable)
- **Python**: 3.11
- **LLM calls**: routed to a local mock server to eliminate network variability

Researchers reproducing the results on different hardware should document their configuration and re-run all experiments.

### 3.2 Experiment E1 — Cold-Start Latency

**Definition**: Time from sending the first request to receiving the first byte of the response, measured on a freshly booted system with no warm process cache.

**Systems under test**: SkillScale Lite, C1 (Docker), C2 (Direct-HTTP), B1 (A2A-MCP-Server), B2 (a2a-gateway).

**Protocol**:
1. Start the system under test from scratch (all processes freshly launched).
2. Send a minimal skill invocation request (`text-summarizer`, 128-byte input).
3. Record the wall-clock time from sending the request to receiving the complete response.
4. Tear down the system between repetitions (for Docker: `docker rm` the container; for others: kill and restart the server process).
5. Repeat 100 times; report median and P95.

**Expected outcome**: SkillScale Lite (native process spawn) is significantly faster than Docker (container startup) and comparable to Direct-HTTP.

### 3.3 Experiment E2 — Hot-Start (Warm) Latency

**Definition**: Per-request latency when the system is already running and the process cache is warm.

**Systems under test**: Same as E1.

**Protocol**:
1. Start the system under test and send 10 warm-up requests (discarded).
2. Send 100 timed requests with 1-second inter-request intervals.
3. Report median and P95.

**Expected outcome**: SkillScale Lite and Direct-HTTP should be similar; Docker incurs container-management overhead even on warm paths.

### 3.4 Experiment E3 — Throughput and Horizontal Scalability

**Definition**: Maximum sustained request throughput (req/s) as the number of skill-server worker processes is varied.

**Systems under test**: SkillScale Lite only (the other systems do not support horizontal scaling without code changes).

**Protocol**:
1. Configure a CPU-bound mock skill with a fixed 200 ms execution time.
2. Launch SkillScale Lite with 1, 2, 4, and 8 skill-server worker threads.
3. Drive load with a fixed pool of 32 concurrent clients until throughput stabilises (at least 60 s of steady-state traffic).
4. Measure throughput as completed requests per second over the steady-state window.
5. Repeat 5 times per worker count; report mean.
6. Compare against the ideal linear scaling curve.

**Expected outcome**: Near-linear throughput increase with worker count.

### 3.5 Experiment E4 — Per-Invocation Memory Footprint

**Definition**: Resident set size (RSS) of all processes belonging to the system while a single skill invocation is in flight.

**Systems under test**: SkillScale Lite, C1 (Docker), C2 (Direct-HTTP).

**Protocol**:
1. Start the system under test.
2. Trigger one skill invocation that runs for exactly 5 seconds (a mock skill with `time.sleep(5)`).
3. While the skill is running, sample RSS of all system processes every 100 ms using `/usr/bin/time -v` (Linux) or `ps -o rss` (macOS).
4. Report the maximum RSS observed during the invocation.
5. Repeat 10 times; report mean.

**Expected outcome**: SkillScale Lite has the lowest RSS because it spawns the Python interpreter only for the skill duration; Docker bears container overhead; Direct-HTTP keeps a persistent server process alive.

### 3.6 Experiment E5 — Protocol Translation Overhead

**Definition**: Latency introduced solely by the gateway's MCP↔A2A translation path, excluding Kafka round-trip and skill execution time.

**Systems under test**: SkillScale Lite gateway only (bypass Kafka by using a mock skill server that replies immediately).

**Protocol**:
1. Deploy a stub skill server that consumes from Kafka and immediately publishes an empty reply.
2. Send 10,000 minimal requests (1 KB payload) through both the MCP path and the A2A path.
3. Measure wall-clock time between the gateway receiving the request and publishing to Kafka (excludes broker and skill time).
4. Report median and P95 for each protocol path.

**Expected outcome**: Sub-millisecond translation latency for both paths.

### 3.7 Experiment E6 — LLM Intent Routing Accuracy

**Definition**: Fraction of coarse-grained requests routed to the correct skill by the LLM intent-matching step.

**Systems under test**: SkillScale Lite only (other systems do not implement LLM routing).

**Protocol**:
1. Create a test set of 200 natural-language skill invocation requests, 50 per skill (`code-complexity`, `dead-code-detector`, `csv-analyzer`, `text-summarizer`), written by three independent annotators to maximise lexical diversity.
2. Submit each request via the coarse-grained A2A endpoint.
3. Record the skill name selected by the LLM.
4. Compute per-skill accuracy and overall accuracy.
5. Evaluate with three different LLM providers (Azure GPT-4o, OpenAI DeepSeek-V3, Zhipu GLM-4.7-FlashX) to assess provider sensitivity.

**Expected outcome**: >90% accuracy across providers; highest confusion between skills in the same category (`code-analysis`).

---

## 4. Reproduction Steps

### Prerequisites

```bash
# Clone SkillScale Lite
git clone https://github.com/xhyccc/skillscale-lite.git
cd skillscale-lite

# Clone all baseline repositories
mkdir -p baselines
git clone https://github.com/GongRzhe/A2A-MCP-Server.git         baselines/a2a-mcp-server
git clone https://github.com/jinyitao123/a2a-gateway.git          baselines/a2a-gateway
git clone https://github.com/peerclaw/peerclaw-server.git         baselines/peerclaw-server
git clone https://github.com/anatolykoptev/openclaw-a2a-bridge.git baselines/openclaw-a2a-bridge
git clone https://github.com/eduardpetraeus-lab/protocol-bridge.git baselines/protocol-bridge
```

### Running the Experiments

```bash
# 1. Set up the environment
cp .env.example .env
# Edit .env with your LLM provider credentials and set LLM_PROVIDER=openai

# 2. Launch SkillScale Lite
./run_all.sh

# 3. Run E1/E2 latency benchmarks
python experiments/bench_latency.py --warmup 10 --repetitions 100

# 4. Run E3 throughput scalability benchmark
python experiments/bench_throughput.py --workers 1 2 4 8 --duration 60

# 5. Run E4 memory benchmark
python experiments/bench_memory.py --repetitions 10

# 6. Run E5 translation overhead benchmark
python experiments/bench_translation.py --requests 10000

# 7. Run E6 LLM routing accuracy evaluation
python experiments/eval_routing.py --test-set experiments/routing_testset.jsonl
```

Each benchmark script writes results to `experiments/results/` as JSON.  The scripts in `experiments/` are the canonical implementations; see the individual script `--help` output for detailed usage.

---

## 5. Benchmark Script Specifications

The following benchmark scripts are to be implemented in `experiments/`:

| Script | Purpose | Key Arguments |
|--------|---------|---------------|
| `bench_latency.py` | E1 + E2: cold/hot latency | `--system`, `--warmup`, `--repetitions` |
| `bench_throughput.py` | E3: throughput vs. workers | `--workers`, `--duration`, `--concurrency` |
| `bench_memory.py` | E4: RSS footprint | `--system`, `--repetitions`, `--skill-duration` |
| `bench_translation.py` | E5: gateway-only overhead | `--requests`, `--payload-size` |
| `eval_routing.py` | E6: LLM routing accuracy | `--test-set`, `--provider` |

All scripts must:
- Accept `--output <path>` to write JSON results.
- Print a summary table to stdout.
- Be deterministic given a fixed random seed (`--seed`).
- Record the system configuration (OS, CPU, RAM, commit SHA) in the output JSON for reproducibility.

---

## 6. Result Reporting

All benchmark results must be reported as:
- **Latency**: median ± standard deviation, P95, across N repetitions (N≥100 for latency, N≥5 for throughput).
- **Throughput**: mean ± standard deviation across 5 independent runs.
- **Memory**: maximum RSS during invocation, mean ± standard deviation across 10 repetitions.
- **Accuracy**: fraction correct per skill and overall, with 95% Wilson confidence intervals.

Raw result JSON files must be committed to `experiments/results/` so that reviewers can verify the numbers independently.

---

## 7. Open Questions for Future Experiments

1. **Multi-skill pipeline latency**: How does end-to-end latency scale when a request involves a chain of 3–5 skills?
2. **Fault-tolerance under load**: How does SkillScale Lite behave when one skill server crashes mid-request?
3. **Cold-start with WebAssembly sandboxing**: What is the latency overhead of enabling the opt-in WASM sandbox?
4. **LLM routing accuracy at scale**: How does routing accuracy degrade as the number of skills grows from 4 to 50?
5. **Comparison with LangChain tool-calling**: How does SkillScale Lite compare to LangChain's tool-selection mechanism in terms of latency and accuracy?

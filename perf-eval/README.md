# perf-eval — SkillScale Lite Performance Evaluation Suite

A **standalone** Rust project (independent `Cargo.toml`, not a member of the
`skillscale-rs` workspace) that benchmarks the performance-critical paths of
SkillScale Lite using [Criterion.rs](https://bheisler.github.io/criterion.rs/).

---

## Benchmark suites

| File | What it measures |
|------|-----------------|
| `benches/concurrent_dispatch.rs` | Concurrent request-dispatch throughput: `Arc<Mutex<HashMap>>` + `tokio::sync::oneshot` channels at 1–500 concurrent tasks; raw pending-map insert/resolve/remove; topic-name generation; UUID v4 generation |
| `benches/json_serialization.rs` | `serde_json` serialize / deserialize / round-trip for `SkillRequest`, `SendTaskParams`, and the gateway reply-consumer's untyped `Value` path |
| `benches/skill_parsing.rs` | AGENTS.md parsing (`parse_agents_md`) at 2–100 skill entries; single `extract_tag` calls; realistic two-skill fixture from the actual repo |

---

## Prerequisites

- Rust toolchain ≥ 1.75 (`rustup update stable`)
- No broker required — all benchmarks run fully in-process

---

## Running the benchmarks

```bash
# From the perf-eval directory:
cd perf-eval

# Run all benchmarks (HTML report saved to target/criterion/)
cargo bench

# Run a single suite
cargo bench --bench concurrent_dispatch
cargo bench --bench json_serialization
cargo bench --bench skill_parsing

# Quick smoke-test (one sample, no statistical analysis)
cargo bench -- --test
```

HTML reports are written to `target/criterion/report/index.html` and can be
opened in any browser for visual comparison across runs.

---

## Interpreting results

Criterion reports each benchmark as:

```
group/benchmark_name   time:   [lower  estimate  upper]
```

- **lower / upper** — 95 % confidence interval
- **estimate** — best estimate of mean execution time
- **change** — percentage change vs. the previous run (shown on re-runs)

A regression exceeding the noise threshold triggers a `Performance has
regressed` warning.

---

## Design notes

- Types in `src/lib.rs` intentionally mirror `skillscale-rs/common` so this
  project compiles without depending on the main workspace.
- The `concurrent_dispatch` suite uses a multi-threaded Tokio runtime
  (`worker_threads = 4`) to surface real scheduler contention.
- All benchmarks call `std::hint::black_box` on their outputs to prevent the
  compiler from optimising away the measured work.

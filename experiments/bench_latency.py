#!/usr/bin/env python3
"""
bench_latency.py — E1 (cold-start) and E2 (hot-start) latency benchmarks.

Measures wall-clock time from sending a minimal skill-invocation request to
receiving the complete response, against multiple system back-ends.

Systems under test (--system flag):
  skillscale   SkillScale Lite (native process spawn + Kafka)
  docker       C1 Docker baseline (container-per-invocation)
  direct-http  C2 Direct-HTTP baseline (synchronous HTTP skill server)
  a2a-mcp      B1 A2A-MCP-Server baseline
  a2a-gateway  B2 a2a-gateway baseline

Usage examples:
  # E2 hot-start, SkillScale Lite only
  python experiments/bench_latency.py --system skillscale --warmup 10 --repetitions 100

  # E1 cold-start, all systems
  python experiments/bench_latency.py --cold-start --repetitions 100 \\
      --output experiments/results/latency_cold.json

  # Deterministic run
  python experiments/bench_latency.py --seed 42 --repetitions 50
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

# Ensure experiments package is importable when run from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    make_a2a_payload,
    print_table,
    summary_stats,
    sys_info,
    write_results,
)

# ── System configurations ─────────────────────────────────────────────────────

SYSTEMS: Dict[str, Dict] = {
    "skillscale": {
        "url": "http://127.0.0.1:8085/v1/agents/code-analysis/skills/text-summarizer/converse",
        "label": "SkillScale Lite",
        "protocol": "A2A",
    },
    "docker": {
        "url": "http://127.0.0.1:9000/invoke",
        "label": "C1 Docker baseline",
        "protocol": "HTTP",
    },
    "direct-http": {
        "url": "http://127.0.0.1:9001/invoke",
        "label": "C2 Direct-HTTP baseline",
        "protocol": "HTTP",
    },
    "a2a-mcp": {
        "url": "http://127.0.0.1:8080/a2a",
        "label": "B1 A2A-MCP-Server",
        "protocol": "A2A",
    },
    "a2a-gateway": {
        "url": "http://127.0.0.1:3000/a2a",
        "label": "B2 a2a-gateway",
        "protocol": "A2A",
    },
}

# Minimal 128-byte input payload (as per E1 spec)
_SAMPLE_INPUT = (
    "Summarise the following: The quick brown fox jumps over the lazy dog. "
    "This is a minimal benchmark payload for cold-start latency measurement."
)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _http_post(url: str, payload: dict, timeout: float = 120.0) -> float:
    """
    POST *payload* as JSON to *url*.  Returns elapsed wall-clock seconds.
    Raises urllib.error.URLError / socket.timeout on failure.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout):
        pass
    return time.perf_counter() - t0


def _is_reachable(url: str, timeout: float = 2.0) -> bool:
    """Return True if the host:port in *url* accepts a TCP connection."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── Cold-start helpers ────────────────────────────────────────────────────────

def _cold_start_round(url: str, timeout: float) -> float:
    """
    Perform a single cold-start measurement.

    Cold-start definition (from PLAN.md §3.2):
      - For Docker: the caller is responsible for container teardown between
        repetitions.  This function simply measures the request latency;
        orchestration is the caller's responsibility.
      - For other systems: the measurement starts when the request is sent to
        the already-fresh process.

    In automated mode we can only measure the request round-trip (since we
    cannot reliably restart peer servers from here).  A warning is printed if
    the system is not reachable.
    """
    return _http_post(url, make_a2a_payload(_SAMPLE_INPUT), timeout=timeout)


# ── Main benchmark loop ───────────────────────────────────────────────────────

def run_benchmark(
    system_key: str,
    repetitions: int,
    warmup: int,
    cold_start: bool,
    timeout: float,
    rng: random.Random,
) -> Dict:
    cfg = SYSTEMS[system_key]
    url = cfg["url"]
    label = cfg["label"]

    if not _is_reachable(url):
        print(f"  [WARN] {label} is not reachable at {url} — skipping.", flush=True)
        return {
            "system": system_key,
            "label": label,
            "url": url,
            "skipped": True,
            "reason": "not reachable",
        }

    samples: List[float] = []

    if not cold_start:
        # E2: send warm-up requests first
        print(f"  Warming up {label} ({warmup} requests)…", flush=True)
        for _ in range(warmup):
            try:
                _http_post(url, make_a2a_payload(_SAMPLE_INPUT), timeout=timeout)
            except Exception:
                pass

    print(
        f"  Measuring {'cold' if cold_start else 'hot'}-start latency for "
        f"{label} ({repetitions} reps)…",
        flush=True,
    )

    for i in range(repetitions):
        # Optional small jitter to avoid request bunching (deterministic via rng)
        jitter = rng.uniform(0.0, 0.05) if not cold_start else 0.0
        if jitter > 0:
            time.sleep(jitter)

        try:
            elapsed = _http_post(url, make_a2a_payload(_SAMPLE_INPUT), timeout=timeout)
            samples.append(elapsed * 1000.0)  # store in ms
        except Exception as exc:
            print(f"    [WARN] request {i+1} failed: {exc}", flush=True)

        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{repetitions} done", flush=True)

    stats = summary_stats(samples)
    return {
        "system": system_key,
        "label": label,
        "url": url,
        "mode": "cold" if cold_start else "hot",
        "warmup": warmup,
        "repetitions": repetitions,
        "successful_samples": len(samples),
        "latency_ms": stats,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E1/E2 latency benchmark for SkillScale Lite and baselines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--system",
        choices=list(SYSTEMS.keys()) + ["all"],
        default="skillscale",
        help="System under test (default: skillscale). Use 'all' for all systems.",
    )
    p.add_argument(
        "--cold-start",
        action="store_true",
        help="Run E1 cold-start mode (no warm-up). Default is E2 hot-start.",
    )
    p.add_argument("--warmup", type=int, default=10, help="Warm-up requests (E2 only). Default: 10.")
    p.add_argument("--repetitions", type=int, default=100, help="Timed repetitions. Default: 100.")
    p.add_argument(
        "--inter-request-delay",
        type=float,
        default=1.0,
        help="Seconds between requests in hot-start mode (E2). Default: 1.0.",
    )
    p.add_argument("--timeout", type=float, default=120.0, help="Per-request HTTP timeout (s). Default: 120.")
    p.add_argument("--seed", type=int, default=0, help="Random seed for reproducibility. Default: 0.")
    p.add_argument(
        "--output",
        metavar="PATH",
        help="Write JSON results to this path (default: experiments/results/latency_<mode>.json).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    mode_tag = "cold" if args.cold_start else "hot"
    default_output = (
        Path(__file__).resolve().parent / "results" / f"latency_{mode_tag}.json"
    )
    output_path = args.output or str(default_output)

    systems_to_run = list(SYSTEMS.keys()) if args.system == "all" else [args.system]

    print("=" * 60)
    print(f"  SkillScale Lite — {'E1 Cold-Start' if args.cold_start else 'E2 Hot-Start'} Latency Benchmark")
    print("=" * 60)
    print(f"  Mode:         {'cold-start (E1)' if args.cold_start else 'hot-start (E2)'}")
    print(f"  Systems:      {', '.join(systems_to_run)}")
    print(f"  Warmup:       {args.warmup if not args.cold_start else 'n/a'}")
    print(f"  Repetitions:  {args.repetitions}")
    print(f"  Seed:         {args.seed}")
    print()

    all_results = []
    for sys_key in systems_to_run:
        print(f"[{sys_key}]")
        result = run_benchmark(
            system_key=sys_key,
            repetitions=args.repetitions,
            warmup=0 if args.cold_start else args.warmup,
            cold_start=args.cold_start,
            timeout=args.timeout,
            rng=rng,
        )
        all_results.append(result)
        print()

    # ── Summary table ─────────────────────────────────────────────────────────
    rows = []
    for r in all_results:
        if r.get("skipped"):
            rows.append([r["label"], "SKIPPED", "-", "-", "-"])
        else:
            s = r["latency_ms"]
            rows.append([
                r["label"],
                r["mode"],
                f"{s['median']:.1f}",
                f"{s['p95']:.1f}",
                f"{s['stdev']:.1f}",
            ])

    print_table(
        ["System", "Mode", "Median (ms)", "P95 (ms)", "Stdev (ms)"],
        rows,
        title=f"Latency Summary — {mode_tag}-start",
    )

    # ── Persist results ───────────────────────────────────────────────────────
    output = {
        "experiment": "E1" if args.cold_start else "E2",
        "mode": mode_tag,
        "parameters": {
            "warmup": args.warmup,
            "repetitions": args.repetitions,
            "seed": args.seed,
            "inter_request_delay": args.inter_request_delay,
        },
        "system_info": sys_info(),
        "results": all_results,
    }
    write_results(output, output_path)


if __name__ == "__main__":
    main()

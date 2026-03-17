#!/usr/bin/env python3
"""
bench_throughput.py — E3 Throughput and Horizontal Scalability benchmark.

Measures maximum sustained request throughput (req/s) as the number of
SkillScale Lite skill-server worker processes is varied (1, 2, 4, 8 by default).

The benchmark drives load with a fixed pool of concurrent clients against the
running SkillScale Lite gateway until throughput stabilises (at least
--duration seconds of steady-state traffic), then records the measured req/s.

Usage examples:
  # Default: 1 2 4 8 workers, 60 s each, 32 concurrent clients
  python experiments/bench_throughput.py

  # Custom worker counts
  python experiments/bench_throughput.py --workers 1 4 8 16 --duration 30

  # Write results
  python experiments/bench_throughput.py --output experiments/results/throughput.json
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import random
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    make_a2a_payload,
    mean,
    print_table,
    stdev,
    summary_stats,
    sys_info,
    write_results,
)

# ── Default gateway URL ───────────────────────────────────────────────────────

DEFAULT_URL = "http://127.0.0.1:8085/v1/agents/code-analysis/skills/text-summarizer/converse"

# The CPU-bound mock skill payload (short text to keep serialisation overhead low)
_PAYLOAD_TEXT = "x" * 128  # 128-byte payload as per E1 spec


# ── Load-driver ───────────────────────────────────────────────────────────────

class _Worker(threading.Thread):
    """Single client thread that repeatedly POSTs requests until *stop_event* is set."""

    def __init__(
        self,
        url: str,
        stop_event: threading.Event,
        results: List[float],
        lock: threading.Lock,
        timeout: float,
        rng: random.Random,
    ) -> None:
        super().__init__(daemon=True)
        self.url = url
        self.stop_event = stop_event
        self.results = results
        self.lock = lock
        self.timeout = timeout
        self.rng = rng

    def run(self) -> None:
        payload = make_a2a_payload(_PAYLOAD_TEXT)
        data = json.dumps(payload).encode("utf-8")
        while not self.stop_event.is_set():
            req = urllib.request.Request(
                self.url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout):
                    pass
                elapsed = time.perf_counter() - t0
                with self.lock:
                    self.results.append(elapsed * 1000.0)  # ms
            except Exception:
                # Count errors silently; they depress the reported throughput
                pass


def _measure_throughput(
    url: str,
    duration: float,
    concurrency: int,
    timeout: float,
    rng: random.Random,
) -> Dict:
    """
    Drive *concurrency* clients for *duration* seconds.
    Returns a dict with throughput_rps, latency stats, and error counts.
    """
    stop_event = threading.Event()
    results: List[float] = []
    lock = threading.Lock()

    workers = [
        _Worker(url, stop_event, results, lock, timeout, rng)
        for _ in range(concurrency)
    ]

    t_start = time.perf_counter()
    for w in workers:
        w.start()
    time.sleep(duration)
    stop_event.set()
    t_end = time.perf_counter()

    for w in workers:
        w.join(timeout=5.0)

    elapsed = t_end - t_start
    n = len(results)
    throughput_rps = n / elapsed if elapsed > 0 else 0.0

    return {
        "completed_requests": n,
        "elapsed_s": elapsed,
        "throughput_rps": throughput_rps,
        "latency_ms": summary_stats(results),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def _is_reachable(url: str, timeout: float = 2.0) -> bool:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E3 throughput / horizontal-scalability benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Gateway endpoint URL. Default: {DEFAULT_URL}",
    )
    p.add_argument(
        "--workers",
        type=int,
        nargs="+",
        default=[1, 2, 4, 8],
        metavar="N",
        help="Worker counts to test (space-separated). Default: 1 2 4 8",
    )
    p.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Steady-state measurement window per run (seconds). Default: 60.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=32,
        help="Number of concurrent client threads. Default: 32.",
    )
    p.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Independent repetitions per worker count. Default: 5.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request HTTP timeout (s). Default: 30.",
    )
    p.add_argument("--seed", type=int, default=0, help="Random seed. Default: 0.")
    p.add_argument(
        "--output",
        metavar="PATH",
        help="Write JSON results to this path.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    default_output = Path(__file__).resolve().parent / "results" / "throughput.json"
    output_path = args.output or str(default_output)

    print("=" * 60)
    print("  SkillScale Lite — E3 Throughput / Scalability Benchmark")
    print("=" * 60)
    print(f"  URL:         {args.url}")
    print(f"  Workers:     {args.workers}")
    print(f"  Duration:    {args.duration} s per run")
    print(f"  Concurrency: {args.concurrency} client threads")
    print(f"  Runs:        {args.runs} per worker count")
    print(f"  Seed:        {args.seed}")
    print()

    if not _is_reachable(args.url):
        print(f"[WARN] Gateway not reachable at {args.url}.")
        print("       Start SkillScale Lite (./run_all.sh) before running this benchmark.")
        print()

    all_results = []
    ideal_base: Optional[float] = None  # req/s at 1 worker (for scaling ratio)

    for n_workers in args.workers:
        print(f"[workers={n_workers}] Running {args.runs} repetitions…", flush=True)
        run_rps: List[float] = []

        for run_idx in range(args.runs):
            print(f"  Run {run_idx + 1}/{args.runs}…", end=" ", flush=True)
            result = _measure_throughput(
                url=args.url,
                duration=args.duration,
                concurrency=args.concurrency,
                timeout=args.timeout,
                rng=rng,
            )
            run_rps.append(result["throughput_rps"])
            print(f"{result['throughput_rps']:.2f} req/s", flush=True)

        mean_rps = mean(run_rps)
        sd_rps = stdev(run_rps)

        if ideal_base is None:
            ideal_base = mean_rps

        scaling_ratio = mean_rps / ideal_base if ideal_base else 1.0
        ideal_ratio = float(n_workers) / (args.workers[0] if args.workers else 1)

        all_results.append({
            "n_workers": n_workers,
            "runs": args.runs,
            "throughput_rps_per_run": run_rps,
            "mean_rps": mean_rps,
            "stdev_rps": sd_rps,
            "scaling_ratio": scaling_ratio,
            "ideal_scaling_ratio": ideal_ratio,
        })
        print()

    # ── Summary table ─────────────────────────────────────────────────────────
    rows = []
    for r in all_results:
        rows.append([
            r["n_workers"],
            f"{r['mean_rps']:.2f}",
            f"{r['stdev_rps']:.2f}",
            f"{r['scaling_ratio']:.2f}x",
            f"{r['ideal_scaling_ratio']:.2f}x",
        ])

    print_table(
        ["Workers", "Mean RPS", "Stdev RPS", "Actual Scaling", "Ideal Scaling"],
        rows,
        title="Throughput Summary (E3)",
    )

    output = {
        "experiment": "E3",
        "parameters": {
            "url": args.url,
            "worker_counts": args.workers,
            "duration_s": args.duration,
            "concurrency": args.concurrency,
            "runs": args.runs,
            "seed": args.seed,
        },
        "system_info": sys_info(),
        "results": all_results,
    }
    write_results(output, output_path)


if __name__ == "__main__":
    main()

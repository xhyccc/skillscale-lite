#!/usr/bin/env python3
"""
bench_memory.py — E4 Per-invocation memory footprint benchmark.

Measures the Resident Set Size (RSS) of all system processes while a single
skill invocation is in flight.  Sampling is performed every 100 ms using
`ps -o rss` (macOS/BSD) or `/proc/<pid>/status` (Linux).

Systems under test (--system):
  skillscale   SkillScale Lite (native process spawn)
  docker       C1 Docker baseline (container-per-invocation)
  direct-http  C2 Direct-HTTP baseline (persistent HTTP server)

Usage examples:
  python experiments/bench_memory.py --system skillscale --repetitions 10
  python experiments/bench_memory.py --system all --output experiments/results/memory.json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import random
import socket
import subprocess
import sys
import threading
import time
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

# ── System configurations ─────────────────────────────────────────────────────

SYSTEMS: Dict[str, Dict] = {
    "skillscale": {
        "url": "http://127.0.0.1:8085/v1/agents/code-analysis/skills/text-summarizer/converse",
        "label": "SkillScale Lite",
        # Pattern to identify system processes (used by ps-based sampler)
        "process_patterns": ["skill-server", "skill_server", "python3", "gateway"],
    },
    "docker": {
        "url": "http://127.0.0.1:9000/invoke",
        "label": "C1 Docker baseline",
        "process_patterns": ["docker", "containerd"],
    },
    "direct-http": {
        "url": "http://127.0.0.1:9001/invoke",
        "label": "C2 Direct-HTTP baseline",
        "process_patterns": ["python3", "uvicorn", "flask"],
    },
}

# 5-second mock skill: short text  (real skill would sleep 5 s; we just measure RSS while waiting)
_SLOW_INPUT = "memory-bench " + ("x" * 200)


# ── RSS sampler ───────────────────────────────────────────────────────────────

def _rss_of_pid_linux(pid: int) -> Optional[int]:
    """Return RSS in KB for *pid* on Linux via /proc/<pid>/status."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        return None
    return None


def _rss_of_pid_ps(pid: int) -> Optional[int]:
    """Return RSS in KB for *pid* via `ps -o rss=`."""
    try:
        out = subprocess.check_output(
            ["ps", "-o", "rss=", "-p", str(pid)],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return int(out.strip())
    except Exception:
        return None


def _rss_of_pid(pid: int) -> Optional[int]:
    if platform.system() == "Linux":
        return _rss_of_pid_linux(pid)
    return _rss_of_pid_ps(pid)


def _find_pids_by_patterns(patterns: List[str]) -> List[int]:
    """Return a list of PIDs whose command line matches any of *patterns*."""
    pids: List[int] = []
    try:
        # pgrep -f pattern on Linux/macOS
        for pat in patterns:
            try:
                out = subprocess.check_output(
                    ["pgrep", "-f", pat], stderr=subprocess.DEVNULL, text=True
                )
                for line in out.splitlines():
                    line = line.strip()
                    if line.isdigit():
                        pids.append(int(line))
            except subprocess.CalledProcessError:
                pass  # No matching processes
    except FileNotFoundError:
        pass
    return list(set(pids))


class RssSampler(threading.Thread):
    """Background thread that samples total RSS of target processes every 100 ms."""

    def __init__(self, patterns: List[str], interval: float = 0.1) -> None:
        super().__init__(daemon=True)
        self.patterns = patterns
        self.interval = interval
        self.samples: List[int] = []  # KB
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            pids = _find_pids_by_patterns(self.patterns)
            total_kb = 0
            for pid in pids:
                kb = _rss_of_pid(pid)
                if kb is not None:
                    total_kb += kb
            if total_kb > 0:
                self.samples.append(total_kb)
            self._stop.wait(self.interval)


# ── HTTP helpers ──────────────────────────────────────────────────────────────

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


def _post_blocking(url: str, text: str, timeout: float) -> None:
    """POST to *url* and block until response is received."""
    data = json.dumps(make_a2a_payload(text)).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout):
        pass


# ── Single-repetition measurement ────────────────────────────────────────────

def _single_rep(
    system_cfg: Dict,
    skill_duration: float,
    timeout: float,
) -> Optional[int]:
    """
    Trigger one skill invocation and return max RSS (KB) observed during it.
    Returns None on failure.
    """
    url = system_cfg["url"]
    patterns = system_cfg.get("process_patterns", [])

    sampler = RssSampler(patterns)
    sampler.start()

    try:
        _post_blocking(url, _SLOW_INPUT, timeout=max(timeout, skill_duration + 10))
    except Exception as exc:
        print(f"    [WARN] request failed: {exc}", flush=True)
        return None
    finally:
        sampler.stop()
        sampler.join(timeout=2.0)

    if not sampler.samples:
        return None
    return max(sampler.samples)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E4 memory footprint benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--system",
        choices=list(SYSTEMS.keys()) + ["all"],
        default="skillscale",
        help="System under test. Default: skillscale.",
    )
    p.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="Repetitions per system. Default: 10.",
    )
    p.add_argument(
        "--skill-duration",
        type=float,
        default=5.0,
        help="Expected skill execution duration (s). Default: 5.",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-request HTTP timeout (s). Default: 60.",
    )
    p.add_argument("--seed", type=int, default=0, help="Random seed. Default: 0.")
    p.add_argument("--output", metavar="PATH", help="Write JSON results to this path.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    _ = random.Random(args.seed)  # Seed RNG for reproducibility even if unused

    default_output = Path(__file__).resolve().parent / "results" / "memory.json"
    output_path = args.output or str(default_output)

    systems_to_run = list(SYSTEMS.keys()) if args.system == "all" else [args.system]

    print("=" * 60)
    print("  SkillScale Lite — E4 Memory Footprint Benchmark")
    print("=" * 60)
    print(f"  Systems:        {', '.join(systems_to_run)}")
    print(f"  Repetitions:    {args.repetitions}")
    print(f"  Skill duration: {args.skill_duration} s")
    print(f"  Seed:           {args.seed}")
    print()

    all_results = []

    for sys_key in systems_to_run:
        cfg = SYSTEMS[sys_key]
        label = cfg["label"]
        url = cfg["url"]

        if not _is_reachable(url):
            print(f"  [WARN] {label} not reachable at {url} — skipping.", flush=True)
            all_results.append({
                "system": sys_key,
                "label": label,
                "skipped": True,
                "reason": "not reachable",
            })
            continue

        print(f"[{sys_key}] Measuring RSS ({args.repetitions} reps)…", flush=True)
        max_rss_samples: List[int] = []

        for i in range(args.repetitions):
            print(f"  Rep {i + 1}/{args.repetitions}…", end=" ", flush=True)
            rss_kb = _single_rep(cfg, args.skill_duration, args.timeout)
            if rss_kb is not None:
                max_rss_samples.append(rss_kb)
                print(f"{rss_kb} KB", flush=True)
            else:
                print("FAILED", flush=True)

        if max_rss_samples:
            stats = summary_stats([float(v) for v in max_rss_samples])
        else:
            stats = {}

        all_results.append({
            "system": sys_key,
            "label": label,
            "url": url,
            "repetitions": args.repetitions,
            "successful_samples": len(max_rss_samples),
            "max_rss_kb": stats,
        })
        print()

    # ── Summary table ─────────────────────────────────────────────────────────
    rows = []
    for r in all_results:
        if r.get("skipped"):
            rows.append([r["label"], "SKIPPED", "-", "-"])
        else:
            s = r.get("max_rss_kb", {})
            rows.append([
                r["label"],
                f"{s.get('mean', float('nan')):.0f}",
                f"{s.get('stdev', float('nan')):.0f}",
                f"{s.get('max', float('nan')):.0f}",
            ])

    print_table(
        ["System", "Mean Max RSS (KB)", "Stdev (KB)", "Abs Max (KB)"],
        rows,
        title="Memory Footprint Summary (E4)",
    )

    output = {
        "experiment": "E4",
        "parameters": {
            "systems": systems_to_run,
            "repetitions": args.repetitions,
            "skill_duration_s": args.skill_duration,
            "seed": args.seed,
        },
        "system_info": sys_info(),
        "results": all_results,
    }
    write_results(output, output_path)


if __name__ == "__main__":
    main()

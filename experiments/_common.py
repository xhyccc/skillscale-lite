"""
experiments/_common.py — Shared utilities for SkillScale Lite benchmark scripts.

Provides:
- sys_info()        – collect OS / CPU / RAM / Git SHA metadata
- make_a2a_payload  – build a minimal A2A TaskSendParams dict
- summary_stats     – compute median, P95, mean, stdev
- print_table       – ASCII table printer
- write_results     – persist JSON results to disk
"""

from __future__ import annotations

import json
import math
import os
import platform
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


# ── System-info collector ─────────────────────────────────────────────────────

def sys_info() -> Dict[str, Any]:
    """Return a dict of system configuration fields for reproducibility."""
    info: Dict[str, Any] = {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version,
        "cpu_count": os.cpu_count(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # RAM (bytes) — best-effort
    try:
        import resource  # Unix only
        info["ram_bytes"] = resource.getrlimit(resource.RLIMIT_AS)[0]
    except Exception:
        pass

    # Total physical RAM via /proc/meminfo (Linux)
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    info["ram_total_kb"] = int(line.split()[1])
                    break
    except Exception:
        pass

    # Fallback: macOS sysctl
    if "ram_total_kb" not in info and platform.system() == "Darwin":
        try:
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            info["ram_total_bytes"] = int(out.strip())
        except Exception:
            pass

    # Git commit SHA
    try:
        repo_root = Path(__file__).resolve().parent.parent
        sha = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        info["git_sha"] = sha
    except Exception:
        info["git_sha"] = "unknown"

    return info


# ── A2A payload builder ───────────────────────────────────────────────────────

def make_a2a_payload(
    text: str,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a minimal A2A TaskSendParams dict (JSON-serialisable)."""
    return {
        "id": task_id or f"task_{uuid.uuid4().hex[:8]}",
        "sessionId": session_id or f"session_{uuid.uuid4().hex[:8]}",
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": text}],
        },
    }


# ── Statistics helpers ────────────────────────────────────────────────────────

def _sorted_copy(values: Sequence[float]) -> List[float]:
    return sorted(values)


def median(values: Sequence[float]) -> float:
    s = _sorted_copy(values)
    n = len(s)
    if n == 0:
        return float("nan")
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def percentile(values: Sequence[float], p: float) -> float:
    """Return the p-th percentile of *values* (0–100), linear interpolation."""
    s = _sorted_copy(values)
    n = len(s)
    if n == 0:
        return float("nan")
    if n == 1:
        return s[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


def mean(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    return sum(values) / len(values)


def stdev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def summary_stats(values: Sequence[float]) -> Dict[str, float]:
    """Return a dict with median, p95, mean, stdev, min, max, count."""
    return {
        "count": len(values),
        "median": median(values),
        "p95": percentile(values, 95),
        "mean": mean(values),
        "stdev": stdev(values),
        "min": min(values) if values else float("nan"),
        "max": max(values) if values else float("nan"),
    }


# ── Wilson confidence interval for proportions ───────────────────────────────

def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Return (lower, upper) 95 % Wilson confidence interval for a proportion."""
    if total == 0:
        return (0.0, 1.0)
    p_hat = successes / total
    denom = 1 + z ** 2 / total
    centre = (p_hat + z ** 2 / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p_hat * (1 - p_hat) / total + z ** 2 / (4 * total ** 2))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


# ── ASCII table printer ───────────────────────────────────────────────────────

def print_table(headers: List[str], rows: List[List[Any]], title: str = "") -> None:
    """Print a simple ASCII table to stdout."""
    if title:
        print(f"\n{title}")
    all_rows = [headers] + [[str(c) for c in row] for row in rows]
    col_widths = [max(len(str(r[i])) for r in all_rows) for i in range(len(headers))]
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    fmt = "| " + " | ".join(f"{{:<{w}}}" for w in col_widths) + " |"
    print(sep)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print(sep)


# ── JSON result writer ────────────────────────────────────────────────────────

def write_results(data: Dict[str, Any], output_path: Optional[str]) -> None:
    """Write *data* as pretty-printed JSON to *output_path* (or stdout if None)."""
    blob = json.dumps(data, indent=2, default=str)
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(blob)
        print(f"\nResults written to: {output_path}")
    else:
        print("\n--- JSON Results ---")
        print(blob)

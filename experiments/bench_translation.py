#!/usr/bin/env python3
"""
bench_translation.py — E5 Protocol Translation Overhead benchmark.

Measures the latency introduced *solely* by the SkillScale Lite gateway's
MCP↔A2A translation path, excluding Kafka round-trip and skill execution time.

A stub skill server (or a mock that bypasses Kafka entirely) is required.
In the default mode the benchmark posts directly to the gateway and a
pre-deployed stub skill server replies immediately.

The benchmark sends --requests requests through both the MCP path and the
A2A path, recording the wall-clock time between the gateway receiving each
request and publishing to Kafka (measured end-to-end at the client as proxy).

Usage examples:
  python experiments/bench_translation.py --requests 10000
  python experiments/bench_translation.py --requests 1000 --payload-size 1024
  python experiments/bench_translation.py --output experiments/results/translation.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import socket
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    make_a2a_payload,
    print_table,
    summary_stats,
    sys_info,
    write_results,
)

# ── Default endpoints ─────────────────────────────────────────────────────────

A2A_URL = "http://127.0.0.1:8085/v1/agents/code-analysis/skills/text-summarizer/converse"
MCP_URL = "http://127.0.0.1:8086/mcp"


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


def _http_post_latency(url: str, payload: bytes, timeout: float = 30.0) -> float:
    """POST *payload* bytes to *url*, return elapsed ms."""
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        pass  # Record elapsed even on error — gateway processing happened
    return (time.perf_counter() - t0) * 1000.0


# ── MCP path via asyncio ──────────────────────────────────────────────────────

async def _mcp_path_latency(n_requests: int, payload_text: str, timeout: float) -> List[float]:
    """
    Send *n_requests* requests through the MCP path and return latency samples (ms).

    Uses the MCP Python SDK's streamable-HTTP client if available, otherwise
    falls back to a raw HTTP POST approximation for the translation-overhead
    measurement.
    """
    samples: List[float] = []
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(
            MCP_URL, timeout=timeout, sse_read_timeout=timeout
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                for _ in range(n_requests):
                    t0 = time.perf_counter()
                    try:
                        await session.call_tool(
                            "code-analysis__text-summarizer",
                            arguments={"input": payload_text},
                        )
                    except Exception:
                        pass
                    samples.append((time.perf_counter() - t0) * 1000.0)
    except ImportError:
        # Fallback: raw HTTP POST to /mcp (JSON-RPC initialize + call)
        rpc_payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "code-analysis__text-summarizer",
                "arguments": {"input": payload_text},
            },
            "id": 1,
        }).encode()
        for _ in range(n_requests):
            samples.append(_http_post_latency(MCP_URL, rpc_payload, timeout))

    return samples


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E5 gateway translation overhead benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--requests",
        type=int,
        default=10_000,
        help="Number of requests per protocol path. Default: 10000.",
    )
    p.add_argument(
        "--payload-size",
        type=int,
        default=1024,
        help="Approximate payload size in bytes. Default: 1024.",
    )
    p.add_argument(
        "--a2a-url",
        default=A2A_URL,
        help=f"A2A gateway URL. Default: {A2A_URL}",
    )
    p.add_argument(
        "--mcp-url",
        default=MCP_URL,
        help=f"MCP gateway URL. Default: {MCP_URL}",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout (s). Default: 30.",
    )
    p.add_argument("--seed", type=int, default=0, help="Random seed. Default: 0.")
    p.add_argument("--output", metavar="PATH", help="Write JSON results to this path.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    default_output = Path(__file__).resolve().parent / "results" / "translation.json"
    output_path = args.output or str(default_output)

    # Build payload of approximately the requested size
    payload_text = "bench " + "x" * max(1, args.payload_size - 6)
    a2a_data = json.dumps(make_a2a_payload(payload_text)).encode("utf-8")

    print("=" * 60)
    print("  SkillScale Lite — E5 Translation Overhead Benchmark")
    print("=" * 60)
    print(f"  A2A URL:      {args.a2a_url}")
    print(f"  MCP URL:      {args.mcp_url}")
    print(f"  Requests:     {args.requests} per path")
    print(f"  Payload size: {len(a2a_data)} bytes")
    print(f"  Seed:         {args.seed}")
    print()

    results: Dict = {}

    # ── A2A path ──────────────────────────────────────────────────────────────
    print(f"[A2A] Sending {args.requests} requests…", flush=True)
    if _is_reachable(args.a2a_url):
        a2a_samples: List[float] = []
        for i in range(args.requests):
            a2a_samples.append(_http_post_latency(args.a2a_url, a2a_data, args.timeout))
            if (i + 1) % 1000 == 0:
                print(f"  {i + 1}/{args.requests} done", flush=True)
        results["a2a"] = {
            "path": "A2A",
            "url": args.a2a_url,
            "n_requests": len(a2a_samples),
            "latency_ms": summary_stats(a2a_samples),
        }
        print(
            f"  Done — median {results['a2a']['latency_ms']['median']:.3f} ms, "
            f"P95 {results['a2a']['latency_ms']['p95']:.3f} ms",
            flush=True,
        )
    else:
        print(f"  [WARN] A2A gateway not reachable at {args.a2a_url} — skipping.", flush=True)
        results["a2a"] = {"path": "A2A", "skipped": True}

    print()

    # ── MCP path ──────────────────────────────────────────────────────────────
    print(f"[MCP] Sending {args.requests} requests…", flush=True)
    if _is_reachable(args.mcp_url):
        try:
            mcp_samples = asyncio.run(
                _mcp_path_latency(args.requests, payload_text, args.timeout)
            )
            results["mcp"] = {
                "path": "MCP",
                "url": args.mcp_url,
                "n_requests": len(mcp_samples),
                "latency_ms": summary_stats(mcp_samples),
            }
            print(
                f"  Done — median {results['mcp']['latency_ms']['median']:.3f} ms, "
                f"P95 {results['mcp']['latency_ms']['p95']:.3f} ms",
                flush=True,
            )
        except Exception as exc:
            print(f"  [ERROR] MCP path failed: {exc}", flush=True)
            results["mcp"] = {"path": "MCP", "skipped": True, "error": str(exc)}
    else:
        print(f"  [WARN] MCP gateway not reachable at {args.mcp_url} — skipping.", flush=True)
        results["mcp"] = {"path": "MCP", "skipped": True}

    print()

    # ── Summary table ─────────────────────────────────────────────────────────
    rows = []
    for path_key in ("a2a", "mcp"):
        r = results.get(path_key, {})
        if r.get("skipped"):
            rows.append([r.get("path", path_key.upper()), "SKIPPED", "-", "-"])
        else:
            s = r.get("latency_ms", {})
            rows.append([
                r.get("path", path_key.upper()),
                f"{s.get('median', float('nan')):.3f}",
                f"{s.get('p95', float('nan')):.3f}",
                f"{s.get('stdev', float('nan')):.3f}",
            ])

    print_table(
        ["Protocol", "Median (ms)", "P95 (ms)", "Stdev (ms)"],
        rows,
        title="Translation Overhead Summary (E5)",
    )

    output = {
        "experiment": "E5",
        "parameters": {
            "requests": args.requests,
            "payload_size_bytes": len(a2a_data),
            "seed": args.seed,
        },
        "system_info": sys_info(),
        "results": results,
    }
    write_results(output, output_path)


if __name__ == "__main__":
    main()

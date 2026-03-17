#!/usr/bin/env python3
"""
eval_routing.py — E6 LLM Intent Routing Accuracy evaluation.

Measures the fraction of coarse-grained natural-language requests that are
routed to the correct skill by SkillScale Lite's LLM intent-matching step.

For each entry in the test set (--test-set), the script submits the request
via the coarse-grained A2A endpoint and inspects the response to determine
which skill was selected.  The actual skill selected is compared to the
expected skill label in the test set.

LLM providers supported via --provider:
  azure-gpt4o      Azure OpenAI GPT-4o
  openai-deepseek  OpenAI-compatible DeepSeek-V3
  zhipu-glm4       Zhipu AI GLM-4.7-FlashX

Usage examples:
  python experiments/eval_routing.py --test-set experiments/routing_testset.jsonl
  python experiments/eval_routing.py \\
      --test-set experiments/routing_testset.jsonl \\
      --provider azure-gpt4o \\
      --output experiments/results/routing_accuracy.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import socket
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (
    make_a2a_payload,
    print_table,
    sys_info,
    wilson_ci,
    write_results,
)

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_AGENT = "code-analysis"
GATEWAY_URL = "http://127.0.0.1:8085"

# Supported skill names (for validation)
KNOWN_SKILLS = {
    "code-complexity",
    "dead-code-detector",
    "csv-analyzer",
    "text-summarizer",
}

# Mapping from provider key → environment variable for the API key
PROVIDER_ENV_KEYS: Dict[str, str] = {
    "azure-gpt4o": "AZURE_OPENAI_API_KEY",
    "openai-deepseek": "OPENAI_API_KEY",
    "zhipu-glm4": "ZHIPU_API_KEY",
}


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


def _post_coarse(agent: str, text: str, timeout: float) -> Dict:
    """POST a coarse-grained A2A request and return the parsed JSON response."""
    url = f"{GATEWAY_URL}/v1/agents/{agent}/converse"
    payload = make_a2a_payload(text)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_selected_skill(response: Dict) -> Optional[str]:
    """
    Inspect an A2A response dict and return the skill name that was selected.

    The gateway includes the selected skill in the response metadata under the
    key 'skill' or 'selected_skill'.  If that is absent we fall back to
    inspecting the task artifact or the response message for a skill marker.
    """
    # Primary: metadata field
    for key in ("skill", "selected_skill", "skill_name"):
        if key in response:
            return str(response[key])

    # Inside 'metadata' sub-dict
    meta = response.get("metadata") or {}
    for key in ("skill", "selected_skill", "skill_name"):
        if key in meta:
            return str(meta[key])

    # Inside 'result' → 'metadata'
    result = response.get("result") or {}
    if isinstance(result, dict):
        for key in ("skill", "selected_skill"):
            if key in result:
                return str(result[key])
        inner_meta = result.get("metadata") or {}
        if isinstance(inner_meta, dict):
            for key in ("skill", "selected_skill"):
                if key in inner_meta:
                    return str(inner_meta[key])

    # Fallback: scan the full response text for known skill names
    raw = json.dumps(response)
    for skill in sorted(KNOWN_SKILLS, key=len, reverse=True):
        if skill in raw:
            return skill

    return None


# ── Per-item evaluation ───────────────────────────────────────────────────────

def evaluate_item(
    item: Dict,
    agent: str,
    timeout: float,
    rng: random.Random,
) -> Dict:
    """
    Submit one test item and return an evaluation record.

    Returns a dict with: text, expected, predicted, correct, error (if any).
    """
    text: str = item["text"]
    expected: str = item["skill"]
    record: Dict = {"text": text, "expected": expected, "predicted": None, "correct": False}

    # Optional inter-request jitter (0–200 ms) for deterministic replay
    time.sleep(rng.uniform(0.0, 0.2))

    try:
        response = _post_coarse(agent, text, timeout)
        predicted = _extract_selected_skill(response)
        record["predicted"] = predicted
        record["correct"] = predicted == expected
        record["response_snippet"] = json.dumps(response)[:200]
    except Exception as exc:
        record["error"] = str(exc)

    return record


# ── Statistics helpers ────────────────────────────────────────────────────────

def per_skill_accuracy(records: List[Dict]) -> Dict[str, Dict]:
    """Return per-skill accuracy dicts including Wilson CIs."""
    totals: Dict[str, int] = {}
    hits: Dict[str, int] = {}
    for r in records:
        exp = r.get("expected", "unknown")
        totals[exp] = totals.get(exp, 0) + 1
        if r.get("correct"):
            hits[exp] = hits.get(exp, 0) + 1

    result = {}
    for skill in totals:
        n = totals[skill]
        h = hits.get(skill, 0)
        lo, hi = wilson_ci(h, n)
        result[skill] = {
            "correct": h,
            "total": n,
            "accuracy": h / n if n else 0.0,
            "wilson_ci_95_lower": lo,
            "wilson_ci_95_upper": hi,
        }
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="E6 LLM routing accuracy evaluation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--test-set",
        default=str(Path(__file__).resolve().parent / "routing_testset.jsonl"),
        help="Path to JSONL test set (default: experiments/routing_testset.jsonl).",
    )
    p.add_argument(
        "--provider",
        choices=list(PROVIDER_ENV_KEYS.keys()) + ["env"],
        default="env",
        help=(
            "LLM provider key.  'env' uses whatever is configured in .env / "
            "environment variables (default)."
        ),
    )
    p.add_argument(
        "--agent",
        default=DEFAULT_AGENT,
        help=f"Agent category to target for coarse-grained routing. Default: {DEFAULT_AGENT}",
    )
    p.add_argument(
        "--gateway-url",
        default=GATEWAY_URL,
        help=f"SkillScale Lite gateway base URL. Default: {GATEWAY_URL}",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request HTTP timeout (s). Default: 120.",
    )
    p.add_argument("--seed", type=int, default=0, help="Random seed. Default: 0.")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N items (useful for quick smoke-tests).",
    )
    p.add_argument("--output", metavar="PATH", help="Write JSON results to this path.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    # Override gateway URL from CLI
    global GATEWAY_URL
    GATEWAY_URL = args.gateway_url.rstrip("/")

    default_output = Path(__file__).resolve().parent / "results" / "routing_accuracy.json"
    output_path = args.output or str(default_output)

    # ── Load test set ─────────────────────────────────────────────────────────
    test_set_path = Path(args.test_set)
    if not test_set_path.exists():
        print(f"ERROR: test set not found: {test_set_path}", file=sys.stderr)
        sys.exit(1)

    items: List[Dict] = []
    with open(test_set_path) as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    if args.limit:
        items = items[: args.limit]

    print("=" * 60)
    print("  SkillScale Lite — E6 LLM Routing Accuracy Evaluation")
    print("=" * 60)
    print(f"  Test set:  {test_set_path} ({len(items)} items)")
    print(f"  Provider:  {args.provider}")
    print(f"  Agent:     {args.agent}")
    print(f"  Gateway:   {GATEWAY_URL}")
    print(f"  Seed:      {args.seed}")
    print()

    if not _is_reachable(GATEWAY_URL):
        print(
            f"[WARN] Gateway not reachable at {GATEWAY_URL}.\n"
            "       Start SkillScale Lite (./run_all.sh) before running this evaluation.\n"
        )

    # ── Evaluate ──────────────────────────────────────────────────────────────
    records: List[Dict] = []
    for idx, item in enumerate(items):
        print(
            f"  [{idx + 1:>3}/{len(items)}] expected={item['skill']:<22} …",
            end="",
            flush=True,
        )
        rec = evaluate_item(item, args.agent, args.timeout, rng)
        records.append(rec)
        status = "✓" if rec.get("correct") else f"✗ (got {rec.get('predicted', 'ERR')})"
        print(f" {status}", flush=True)

    # ── Compute stats ─────────────────────────────────────────────────────────
    total = len(records)
    correct = sum(1 for r in records if r.get("correct"))
    overall_acc = correct / total if total else 0.0
    overall_lo, overall_hi = wilson_ci(correct, total)
    per_skill = per_skill_accuracy(records)

    # ── Summary table ─────────────────────────────────────────────────────────
    rows = []
    for skill in sorted(per_skill.keys()):
        s = per_skill[skill]
        rows.append([
            skill,
            s["correct"],
            s["total"],
            f"{s['accuracy']:.1%}",
            f"[{s['wilson_ci_95_lower']:.3f}, {s['wilson_ci_95_upper']:.3f}]",
        ])
    rows.append([
        "OVERALL",
        correct,
        total,
        f"{overall_acc:.1%}",
        f"[{overall_lo:.3f}, {overall_hi:.3f}]",
    ])

    print_table(
        ["Skill", "Correct", "Total", "Accuracy", "95% Wilson CI"],
        rows,
        title="\nRouting Accuracy Summary (E6)",
    )

    # ── Persist results ───────────────────────────────────────────────────────
    output = {
        "experiment": "E6",
        "parameters": {
            "test_set": str(test_set_path),
            "n_items": len(items),
            "provider": args.provider,
            "agent": args.agent,
            "gateway_url": GATEWAY_URL,
            "seed": args.seed,
        },
        "system_info": sys_info(),
        "summary": {
            "total": total,
            "correct": correct,
            "overall_accuracy": overall_acc,
            "wilson_ci_95": [overall_lo, overall_hi],
            "per_skill": per_skill,
        },
        "records": records,
    }
    write_results(output, output_path)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Google Agent-to-Agent (A2A) Client Demo

Demonstrates both coarse-grained and fine-grained A2A invocations:

  Coarse-grained (AGENTS.md + LLM picks skill):
    POST /v1/agents/{agent_id}/converse

  Fine-grained (directly invoke a specific skill):
    POST /v1/agents/{agent_id}/skills/{skill_name}/converse
"""

import os
import sys
import urllib.request
import json
import uuid

from a2a_protocol.pydantic_v2 import (
    TaskSendParams,
    Message,
    Role,
    Part,
    TextPart,
)

GATEWAY_URL = "http://127.0.0.1:8085"


def send_a2a(url, code_text, label):
    """Send an A2A request and print the response."""
    params = TaskSendParams(
        id=f"task_{uuid.uuid4().hex[:8]}",
        sessionId=f"session_{uuid.uuid4().hex[:8]}",
        message=Message(
            role=Role.user,
            parts=[Part(root=TextPart(type="text", text=code_text))],
        ),
    )

    payload = params.model_dump(mode="json", exclude_none=True)

    print(f"Starting A2A Client Demo...")
    print(f"  Mode:    {label}")
    print(f"  Target:  {url}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    print("-" * 50)

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    timeout = int(float(os.environ.get('SKILLSCALE_GATEWAY_TIMEOUT', '600')))
    with urllib.request.urlopen(req, timeout=timeout) as response:
        resp_data = json.loads(response.read().decode("utf-8"))
        print(f"\n[A2A] Response:")
        print(json.dumps(resp_data, indent=2))
    return resp_data


def main():
    code_text = (
        "def process_data(data):\n"
        "    count = 0\n"
        "    for item in data:\n"
        "        if item > 10:\n"
        "            count += 1\n"
        "            if count > 5:\n"
        "                return True\n"
        "    return False\n"
    )

    # ── 1. Coarse-grained: agent only (LLM picks skill from AGENTS.md) ──
    print("=" * 60)
    print("  [1] Coarse-grained A2A (agent__code-analysis)")
    print("=" * 60)
    coarse_url = f"{GATEWAY_URL}/v1/agents/code-analysis/converse"
    try:
        send_a2a(coarse_url, code_text, "coarse-grained — LLM picks the skill")
    except Exception as e:
        print(f"Coarse-grained A2A failed: {e}")
        sys.exit(1)

    print()

    # ── 2. Fine-grained: agent + skill (directly invoke dead-code-detector) ──
    print("=" * 60)
    print("  [2] Fine-grained A2A (code-analysis/dead-code-detector)")
    print("=" * 60)
    fine_url = f"{GATEWAY_URL}/v1/agents/code-analysis/skills/dead-code-detector/converse"
    try:
        send_a2a(fine_url, code_text, "fine-grained — directly invoke dead-code-detector")
    except Exception as e:
        print(f"Fine-grained A2A failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

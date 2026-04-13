#!/usr/bin/env python3
"""Ollama-backed RTC agent CLI.

Mirrors the Claude CLI contract used by runner/agent_exec.py:
  - system prompt via --system-prompt <text>
  - user prompt (mono context) via stdin
  - env vars OLLAMA_HOST and OLLAMA_MODEL select backend/model

The model is expected to reply with one or more shell commands (curl)
that submit the chosen action back to the engine. We extract lines
starting with `curl ` (including continuations) from the response and
execute them via /bin/sh so the action actually lands, matching how
the Claude CLI's bash tool would have run them.
"""

import argparse
import os
import re
import subprocess
import sys

import httpx

DEFAULT_HOST = "http://192.168.20.8:11434"
DEFAULT_MODEL = "gemma4:latest"


def _extract_curl_blocks(text: str) -> list[str]:
    """Pull curl commands out of the model's free-form reply.

    Handles fenced code blocks and line-continuation backslashes. Returns
    a list of shell-ready command strings.
    """
    blocks: list[str] = []
    fence_re = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
    candidates = fence_re.findall(text)
    candidates.append(text)

    for blob in candidates:
        lines = blob.splitlines()
        current: list[str] = []
        in_curl = False
        for line in lines:
            stripped = line.strip()
            if not in_curl and stripped.startswith("curl "):
                in_curl = True
                current = [line]
                if not stripped.endswith("\\"):
                    blocks.append("\n".join(current))
                    in_curl = False
                continue
            if in_curl:
                current.append(line)
                if not stripped.endswith("\\"):
                    blocks.append("\n".join(current))
                    in_curl = False

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            unique.append(b)
    return unique


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-prompt", default="")
    args = parser.parse_args()

    host = os.environ.get("OLLAMA_HOST", DEFAULT_HOST)
    model = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
    user_prompt = sys.stdin.read()

    messages = []
    if args.system_prompt:
        messages.append({"role": "system", "content": args.system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    resp = httpx.post(
        f"{host}/api/chat",
        json={"model": model, "messages": messages, "stream": False},
        timeout=300.0,
    )
    resp.raise_for_status()
    reply = resp.json().get("message", {}).get("content", "")

    print(reply, flush=True)

    commands = _extract_curl_blocks(reply)
    if not commands:
        print("[ollama_agent] no curl command found in reply", file=sys.stderr)
        return 1

    for cmd in commands:
        print(f"\n[ollama_agent] executing:\n{cmd}", file=sys.stderr)
        subprocess.run(cmd, shell=True, check=False)

    return 0


if __name__ == "__main__":
    sys.exit(main())

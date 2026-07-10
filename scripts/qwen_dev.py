#!/usr/bin/env python3
"""Dispatch a development task to a Qwen model; stage generated files for review.

QuotePilot is not only powered by Qwen at runtime — it was largely WRITTEN by
Qwen models, orchestrated by a supervising agent that reviews and accepts the
output. This script is the dispatch harness.

Usage:
    python scripts/qwen_dev.py TASK.md --model qwen3-coder-plus --out staging/

The task file is sent as the user prompt. The model must emit files as:

    ### FILE: relative/path.py
    ```python
    ...complete file...
    ```

Files are written under --out (never directly into src/). Token usage is
appended to docs/qwen_dev_ledger.jsonl with an estimated USD cost.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
import os  # noqa: E402

LEDGER = ROOT / "docs" / "qwen_dev_ledger.jsonl"
BUDGET_ABORT_USD = 35.0  # hard stop well under the $40 credit

# USD per 1M tokens (input, output) — conservative estimates for budget
# control, calibrated against docs.qwencloud.com pricing 2026-07 (qwen3.7-max
# 2.5/7.5, qwen3.7-plus 0.4/1.6, qwen3.6-flash 0.25/1.5; coder-plus assumed).
PRICES = {
    "qwen-max": (2.5, 7.5),
    "qwen-plus": (0.4, 1.6),
    "qwen-flash": (0.25, 1.5),
    "qwen3-coder-plus": (2.0, 8.0),
}

SYSTEM = """You are a senior Python engineer generating production code for an
existing codebase. Follow the interfaces given in the task EXACTLY — matching
names, signatures, and types — because your code must drop into the project
without edits. Rules:
- Output COMPLETE files only. No placeholders, no '...', no 'rest unchanged'.
- Before each file, print a header line:  ### FILE: relative/path
- Then the file in a single fenced code block.
- No prose outside file blocks except a one-line note at the very end.
- Standard library + the project's declared dependencies only.
- Type hints everywhere; docstrings where non-obvious; no dead code."""

FILE_RE = re.compile(r"^### FILE:\s*(.+?)\s*$\n+```[a-zA-Z0-9]*\n(.*?)^```", re.M | re.S)


def spent_so_far() -> float:
    if not LEDGER.exists():
        return 0.0
    total = 0.0
    for line in LEDGER.read_text().splitlines():
        total += json.loads(line).get("est_cost_usd", 0.0)
    return total


def estimate(model: str, p: int, c: int) -> float:
    inp, out = PRICES.get(model, (2.0, 8.0))
    return round(p / 1e6 * inp + c / 1e6 * out, 6)


def dispatch(task_path: Path, model: str, out_dir: Path, max_tokens: int, rounds: int) -> None:
    spent = spent_so_far()
    if spent >= BUDGET_ABORT_USD:
        sys.exit(f"BUDGET STOP: ledger already at ${spent:.2f} (limit ${BUDGET_ABORT_USD})")

    client = OpenAI(
        api_key=os.environ["QWEN_API_KEY"],
        base_url=os.getenv(
            "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        ),
    )
    task = task_path.read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": task},
    ]
    full_text, p_tokens, c_tokens, calls = "", 0, 0, 0

    for round_no in range(rounds):
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.2, max_tokens=max_tokens
        )
        calls += 1
        choice = resp.choices[0]
        chunk = choice.message.content or ""
        full_text += chunk
        if resp.usage:
            p_tokens += resp.usage.prompt_tokens
            c_tokens += resp.usage.completion_tokens
        if choice.finish_reason != "length":
            break
        messages.append({"role": "assistant", "content": chunk})
        messages.append(
            {"role": "user", "content": "Continue EXACTLY where you stopped. Do not repeat anything."}
        )
        print(f"  [continuation {round_no + 1}: output was truncated]", file=sys.stderr)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_raw_response.md").write_text(full_text, encoding="utf-8")

    written: list[str] = []
    for match in FILE_RE.finditer(full_text):
        rel = match.group(1).strip().lstrip("/")
        if ".." in rel:
            print(f"  SKIPPED unsafe path: {rel}", file=sys.stderr)
            continue
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(match.group(2), encoding="utf-8")
        written.append(rel)

    cost = estimate(model, p_tokens, c_tokens)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "task": task_path.name,
                    "model": model,
                    "calls": calls,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "est_cost_usd": cost,
                    "files": written,
                }
            )
            + "\n"
        )
    print(f"model={model} calls={calls} tokens={p_tokens}+{c_tokens} est=${cost:.4f}")
    print(f"cumulative ledger: ${spent_so_far():.4f} / ${BUDGET_ABORT_USD}")
    print("files staged:" if written else "WARNING: no files parsed — inspect _raw_response.md")
    for rel in written:
        print(f"  {out_dir / rel}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("task", type=Path)
    ap.add_argument("--model", default="qwen3-coder-plus", choices=list(PRICES))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-tokens", type=int, default=8000)  # qwen-max caps at 8192
    ap.add_argument("--rounds", type=int, default=4, help="max continuation rounds")
    args = ap.parse_args()
    dispatch(args.task, args.model, args.out, args.max_tokens, args.rounds)


if __name__ == "__main__":
    main()

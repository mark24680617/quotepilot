"""The autopilot: one run = email in → approved artifacts out.

Stage graph (sequential, with one HITL pause):

  intake(qwen-flash) → fx → pricing(+qwen3-coder-plus matching)
      → risk(rules + qwen-flash sweep) → drafting(qwen-max)
      → assemble → ⏸ HITL gate → render artifacts + audit

The stage logic lives in `core` so the AgentScope agent path can reuse it.
"""

from __future__ import annotations

import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import config, core, llm
from .audit import AuditTrail
from .hitl import ApprovalGate, summarize
from .models import RunResult


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def run_autopilot(
    raw_email: str,
    gate: ApprovalGate,
    runs_dir: Path | None = None,
    source_name: str = "stdin",
    progress: Optional[Callable[[str], None]] = None,
    profile=None,
) -> RunResult:
    """progress, if given, is called with each stage name as it completes."""
    run_id = _new_run_id()
    run_dir = (runs_dir or config.RUNS_DIR) / run_id
    audit = AuditTrail(run_dir)
    usage = llm.UsageTracker()
    audit.log("run_started", run_id=run_id, source=source_name)

    t_last = time.perf_counter()

    def on_stage(stage: str) -> None:
        nonlocal t_last
        audit.log(
            "stage_completed", stage=stage, seconds=round(time.perf_counter() - t_last, 2)
        )
        t_last = time.perf_counter()
        if progress:
            progress(stage)

    quote, inquiry = core.assemble_quote_draft(raw_email, usage, on_stage, profile=profile)

    (run_dir / "inquiry.json").write_text(inquiry.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "quote.json").write_text(quote.model_dump_json(indent=2), encoding="utf-8")
    audit.log(
        "quote_assembled",
        quote_number=quote.quote_number,
        total_usd=str(quote.total_usd),
        total_cny=str(quote.total_cny),
        flags=[f.code for f in quote.risk_flags],
    )

    audit.log("hitl_requested")
    decision = gate.review(quote)
    # The web gate lets the reviewer edit line items before deciding (the edit
    # endpoint replaces gate.quote) — pick up the edited quote so quote.json,
    # the summary and the rendered artifacts match what was actually approved.
    edited = getattr(gate, "quote", None)
    if edited is not None and edited is not quote:
        quote = edited
        (run_dir / "quote.json").write_text(quote.model_dump_json(indent=2), encoding="utf-8")
        audit.log(
            "quote_edited_at_gate",
            total_usd=str(quote.total_usd),
            total_cny=str(quote.total_cny),
        )
    audit.log("hitl_decision", action=decision.action, notes=decision.notes)

    artifacts = {
        "inquiry": str(run_dir / "inquiry.json"),
        "quote_json": str(run_dir / "quote.json"),
        "summary": str(run_dir / "summary.txt"),
    }
    (run_dir / "summary.txt").write_text(summarize(quote), encoding="utf-8")

    if decision.action == "approve":
        artifacts.update(core.render_artifacts(quote, run_dir))
        audit.log("artifacts_rendered", **{k: v for k, v in artifacts.items()})

    audit.log("run_finished", decision=decision.action, usage=usage.by_model)
    return RunResult(
        run_id=run_id,
        decision=decision,
        quote=quote,
        artifacts=artifacts,
        usage=usage.by_model,
    )

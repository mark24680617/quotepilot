"""The autopilot: one run = email in → approved artifacts out.

Stage graph (sequential, with one HITL pause):

  intake(qwen-flash) → fx → pricing(+qwen3-coder-plus matching)
      → risk(rules + qwen-flash sweep) → drafting(qwen-max)
      → assemble → ⏸ HITL gate → render artifacts + audit
"""

from __future__ import annotations

import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from . import config, llm
from .audit import AuditTrail
from .hitl import ApprovalGate, summarize
from .models import Customer, QuoteDraft, RunResult
from .stages import drafting, fx, intake, pricing, render, risk


def _new_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def _quote_number() -> str:
    return f"LUQ-Q-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(2).upper()}"


def run_autopilot(
    raw_email: str,
    gate: ApprovalGate,
    runs_dir: Path | None = None,
    source_name: str = "stdin",
    progress: Optional[Callable[[str], None]] = None,
) -> RunResult:
    """progress, if given, is called with each stage name as it completes."""
    run_id = _new_run_id()
    run_dir = (runs_dir or config.RUNS_DIR) / run_id
    audit = AuditTrail(run_dir)
    usage = llm.UsageTracker()
    audit.log("run_started", run_id=run_id, source=source_name)

    def timed(stage: str, fn, *args, **kwargs):
        t0 = time.perf_counter()
        out = fn(*args, **kwargs)
        audit.log("stage_completed", stage=stage, seconds=round(time.perf_counter() - t0, 2))
        if progress:
            progress(stage)
        return out

    inquiry = timed("intake", intake.parse_inquiry, raw_email, usage)
    (run_dir / "inquiry.json").write_text(
        inquiry.model_dump_json(indent=2), encoding="utf-8"
    )

    rate = timed("fx", fx.get_usd_cny)
    lines, unmatched = timed("pricing", pricing.price_inquiry, inquiry, rate, usage)
    subtotal, discount, total, total_cny = pricing.totals(lines, rate)

    flags = timed("risk_rules", risk.rule_flags, inquiry, lines, unmatched, total, raw_email)
    flags += timed("risk_llm_sweep", risk.llm_sweep, raw_email, inquiry, usage)

    cover = timed("drafting", drafting.draft_cover, inquiry, lines, flags, usage)

    today = date.today()
    extra_en, extra_zh = [], []
    if any(f.code == "FAPIAO_REQUEST" for f in flags):
        extra_en.append(config.TERMS["tax_note_en"])
        extra_zh.append(config.TERMS["tax_note_zh"])

    quote = QuoteDraft(
        quote_number=_quote_number(),
        issue_date=today,
        valid_until=today + timedelta(days=config.QUOTE_VALIDITY_DAYS),
        customer=Customer(
            contact_name=inquiry.contact_name or "—",
            company=inquiry.company or "—",
            email=inquiry.email or "—",
        ),
        lines=lines,
        unmatched=unmatched,
        subtotal_usd=subtotal,
        discount_usd=discount,
        total_usd=total,
        total_cny=total_cny,
        fx=rate,
        cover=cover,
        payment_terms_en=config.TERMS["payment_en"],
        payment_terms_zh=config.TERMS["payment_zh"],
        legal_en=config.TERMS["legal_en"],
        legal_zh=config.TERMS["legal_zh"],
        extra_notes_en=extra_en,
        extra_notes_zh=extra_zh,
        risk_flags=flags,
    )
    (run_dir / "quote.json").write_text(quote.model_dump_json(indent=2), encoding="utf-8")
    audit.log(
        "quote_assembled",
        quote_number=quote.quote_number,
        total_usd=str(total),
        total_cny=str(total_cny),
        flags=[f.code for f in flags],
    )

    audit.log("hitl_requested")
    decision = gate.review(quote)
    audit.log("hitl_decision", action=decision.action, notes=decision.notes)

    artifacts = {
        "inquiry": str(run_dir / "inquiry.json"),
        "quote_json": str(run_dir / "quote.json"),
        "summary": str(run_dir / "summary.txt"),
    }
    (run_dir / "summary.txt").write_text(summarize(quote), encoding="utf-8")

    if decision.action == "approve":
        html_path = run_dir / f"{quote.quote_number}.html"
        html_path.write_text(render.render_quote_html(quote), encoding="utf-8")
        email_path = run_dir / "reply_email.md"
        email_path.write_text(render.render_reply_email(quote), encoding="utf-8")
        artifacts["quote_html"] = str(html_path)
        artifacts["reply_email"] = str(email_path)
        audit.log("artifacts_rendered", quote_html=str(html_path), reply_email=str(email_path))

    audit.log("run_finished", decision=decision.action, usage=usage.by_model)
    return RunResult(
        run_id=run_id,
        decision=decision,
        quote=quote,
        artifacts=artifacts,
        usage=usage.by_model,
    )

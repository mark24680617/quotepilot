"""Human-in-the-loop approval gate.

The autopilot pauses exactly once — after the full quote is assembled and
before anything is "sent". Gates are pluggable: CLI today, web dashboard next.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .models import Decision, QuoteDraft

_SEV_ICON = {"info": "ℹ️ ", "warn": "⚠️ ", "block": "⛔ "}


def summarize(quote: QuoteDraft) -> str:
    lines = [
        f"Quote {quote.quote_number}  →  {quote.customer.company} ({quote.customer.contact_name})",
        f"Valid until {quote.valid_until.isoformat()}   FX USD/CNY {quote.fx.rate}"
        + ("  [OFFLINE RATE]" if quote.fx.offline else f"  ({quote.fx.source})"),
        "-" * 72,
    ]
    for l in quote.lines:
        disc = f"  -{l.discount_pct}%" if l.discount_pct else ""
        lines.append(
            f"  {l.sku:<8} {l.name_en[:38]:<40} {l.quantity:>8} × {l.unit_price_usd:>9}{disc}"
            f"  = {l.line_total_usd:>12,}"
        )
    lines += [
        "-" * 72,
        f"  Subtotal USD {quote.subtotal_usd:>12,}   Discount USD {quote.discount_usd:>10,}",
        f"  TOTAL    USD {quote.total_usd:>12,}   ≈ CNY {quote.total_cny:>14,}",
    ]
    if quote.unmatched:
        lines.append("  Unpriced requests:")
        for u in quote.unmatched:
            lines.append(f"    • {u.product_name} — {u.reason}")
    if quote.risk_flags:
        lines.append("  Risk flags:")
        for f in quote.risk_flags:
            lines.append(f"    {_SEV_ICON[f.severity]}[{f.code}] {f.message_en}")
    return "\n".join(lines)


class ApprovalGate(Protocol):
    def review(self, quote: QuoteDraft) -> Decision: ...


class AutoApproveGate:
    """Non-interactive gate for demos/CI. Blocks are still refused."""

    def review(self, quote: QuoteDraft) -> Decision:
        blocked = any(f.severity == "block" for f in quote.risk_flags)
        return Decision(
            action="reject" if blocked else "approve",
            notes="auto-rejected: blocking risk flag" if blocked else "auto-approved (demo mode)",
            decided_at=datetime.now(timezone.utc),
        )


class CLIGate:
    """Interactive terminal approval."""

    def review(self, quote: QuoteDraft) -> Decision:
        print("\n" + summarize(quote) + "\n")
        blocked = any(f.severity == "block" for f in quote.risk_flags)
        if blocked:
            print("⛔ Blocking flag present — approval disabled, reject or edit only.")
        while True:
            choice = input("[a]pprove / [e]dit notes / [r]eject > ").strip().lower()
            now = datetime.now(timezone.utc)
            if choice in ("a", "approve") and not blocked:
                return Decision(action="approve", decided_at=now)
            if choice in ("e", "edit"):
                notes = input("Notes for revision: ").strip()
                return Decision(action="edit", notes=notes, decided_at=now)
            if choice in ("r", "reject"):
                notes = input("Reason (optional): ").strip() or None
                return Decision(action="reject", notes=notes, decided_at=now)
            print("Please answer a / e / r.")

"""Regression: a quote edited at the web gate must be the one rendered."""
import json
from datetime import datetime, timezone
from decimal import Decimal

from quotepilot import orchestrator
from quotepilot.models import Decision

from test_web import make_quote


class EditingGate:
    """Simulates the web flow: reviewer edits the quote, then approves."""

    def __init__(self, edited_quote):
        self.quote = None
        self._edited = edited_quote

    def review(self, quote):
        # the /edit endpoint replaces gate.quote with a repriced copy
        self.quote = self._edited
        return Decision(action="approve", notes=None, decided_at=datetime.now(timezone.utc))


def test_edited_quote_reaches_artifacts(tmp_path, monkeypatch):
    original = make_quote()
    edited = make_quote()
    edited.total_usd = Decimal("32550.00")
    edited.quote_number = "LUQ-Q-TEST-EDITED"

    monkeypatch.setattr(
        orchestrator.core, "assemble_quote_draft",
        lambda raw, usage, on_stage=None, profile=None: (original, original.customer),
    )

    result = orchestrator.run_autopilot(
        "dummy inquiry email long enough", EditingGate(edited), runs_dir=tmp_path
    )

    assert result.quote.quote_number == "LUQ-Q-TEST-EDITED"
    run_dir = tmp_path / result.run_id
    saved = json.loads((run_dir / "quote.json").read_text())
    assert saved["quote_number"] == "LUQ-Q-TEST-EDITED"
    assert saved["total_usd"] == "32550.00"
    # rendered quote HTML exists and carries the edited quote number
    html = (run_dir / f"{edited.quote_number}.html").read_text()
    assert "LUQ-Q-TEST-EDITED" in html

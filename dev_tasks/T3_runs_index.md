# Task T3: runs directory index helper + unit tests

## File 1: `src/quotepilot/web/runs_index.py`

A small, dependency-light module that scans the `runs/` directory produced by
the QuotePilot orchestrator and returns an index for the dashboard archive.

Each run directory `runs/<run_id>/` may contain:
- `audit.jsonl` — JSON lines; first line has `{"event":"run_started","ts":...}`;
  a line with `{"event":"run_finished","decision":"approve"|"reject"|...}` may exist.
- `quote.json` — serialized quote: keys include `quote_number` (str),
  `total_usd` (str), and `customer` (object with `company` str).
- `<quote_number>.html` — present only for approved runs.

Directories may be partial (crashed runs): any file may be missing or
malformed. Never raise; degrade to None fields.

```python
from pathlib import Path
from pydantic import BaseModel

class RunIndexEntry(BaseModel):
    run_id: str
    ts: str | None = None            # run_started ts
    quote_number: str | None = None
    company: str | None = None
    total_usd: str | None = None     # keep as string as stored
    decision: str | None = None      # from run_finished event
    has_html: bool = False           # any *.html file present

def list_runs(runs_dir: Path, limit: int = 50) -> list[RunIndexEntry]:
    """Newest first (run_id sorts chronologically); missing dir -> []."""
```

Rules: only consider subdirectories; skip files. `has_html` = any `*.html`
glob. Read files with `encoding="utf-8"`, wrap every per-run parse step in
try/except. Return at most `limit` entries.

## File 2: `tests/test_runs_index.py`

pytest tests using `tmp_path`:
1. missing runs dir → `[]`
2. full happy run dir (audit.jsonl with run_started + run_finished, quote.json,
   a `.html` file) → all fields populated, `has_html is True`
3. partial dir (only malformed `quote.json` containing `not json`) → entry
   exists with `run_id` set and other fields None/False
4. ordering + limit: three dirs named `20260101-000000-aa`,
   `20260102-000000-bb`, `20260103-000000-cc`, `limit=2` → returns cc then bb

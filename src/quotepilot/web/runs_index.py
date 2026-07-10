from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel
import json

class RunIndexEntry(BaseModel):
    run_id: str
    ts: Optional[str] = None
    quote_number: Optional[str] = None
    company: Optional[str] = None
    total_usd: Optional[str] = None
    decision: Optional[str] = None
    has_html: bool = False


def list_runs(runs_dir: Path, limit: int = 50) -> List[RunIndexEntry]:
    """Newest first (run_id sorts chronologically); missing dir -> []."""
    if not runs_dir.exists() or not runs_dir.is_dir():
        return []

    entries = []
    for subdir in runs_dir.iterdir():
        if not subdir.is_dir():
            continue

        run_id = subdir.name
        entry = RunIndexEntry(run_id=run_id)

        # Parse audit.jsonl
        audit_path = subdir / "audit.jsonl"
        if audit_path.exists():
            try:
                with open(audit_path, "r", encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("event") == "run_started":
                            entry.ts = data.get("ts")
                    # Look for run_finished event
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("event") == "run_finished":
                                entry.decision = data.get("decision")
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception:
                pass  # Ignore parsing errors

        # Parse quote.json
        quote_path = subdir / "quote.json"
        if quote_path.exists():
            try:
                with open(quote_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entry.quote_number = data.get("quote_number")
                    entry.total_usd = data.get("total_usd")
                    customer = data.get("customer")
                    if isinstance(customer, dict):
                        entry.company = customer.get("company")
            except Exception:
                pass  # Ignore parsing errors

        # Check for any .html file
        html_files = list(subdir.glob("*.html"))
        entry.has_html = len(html_files) > 0

        entries.append(entry)

    # Sort by run_id descending (newest first), since run_ids are timestamp-based
    entries.sort(key=lambda e: e.run_id, reverse=True)
    
    # Return at most `limit` entries
    return entries[:limit]

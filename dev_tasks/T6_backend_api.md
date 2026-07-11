# Task T6: JSON API + CORS for the QuotePilot backend

The dashboard is being split: a static frontend (GitHub Pages) will call this
FastAPI backend cross-origin. The backend runs on Alibaba Cloud Function
Compute behind the fcapp.run system domain, which force-downloads HTML page
navigations — but fetch()/XHR is unaffected. Therefore: add JSON endpoints +
CORS while KEEPING all existing server-rendered routes untouched (they still
serve local dev and a future custom domain).

## Changes to `src/quotepilot/web/app.py` (emit the COMPLETE updated file)

### 1. CORS
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # anonymous public demo API — no cookies/credentials
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 2. New JSON endpoints (reuse existing helpers; do NOT duplicate logic)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/bootstrap` | `{"samples": [names...], "submissions": [sub_view...newest first], "archived": [RunIndexEntry.model_dump()...]}` — same data the dashboard route gathers; factor the gathering into a helper shared by both routes |
| POST | `/api/submit` | body JSON `{"email_text": str}`; same validation as /submit (strip, min 20 chars → 422); create submission + thread exactly like /submit (factor shared logic into a helper `_start_submission(email_text) -> str` used by both); returns `{"sid": sid}` |
| GET | `/api/s/{sid}` | `{"s": sub_view(sub), "summary": summarize(...) if awaiting_approval else None}` ; 404 unknown |
| POST | `/api/s/{sid}/decision` | body JSON `{"action": "approve"|"reject", "notes": str|null}`; same guards as the form endpoint (404 unknown sid, 400 bad action, 409 blocked-approve or resolve failure); returns `{"ok": true, "status": <submission status after resolve>}` |

Use pydantic models for the two JSON request bodies. Note the status right
after resolve() may still be "awaiting_approval" for an instant — read the
submission status AFTER calling resolve and simply report whatever it is;
the frontend polls anyway.

### 3. Keep everything else identical
No changes to WebGate, sub_view, existing routes, or templates. The complete
current file is below — modify it faithfully:

```python
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from quotepilot.config import DATA_DIR, RUNS_DIR
from quotepilot.hitl import summarize
from quotepilot.models import Decision, QuoteDraft, RunResult
from quotepilot.orchestrator import run_autopilot
from quotepilot.stages.render import render_quote_html


class WebGate:
    quote: QuoteDraft | None
    
    def __init__(self, on_review: Callable[[], None]) -> None:
        self.quote = None
        self.on_review = on_review
        self.event = threading.Event()
        self._decision: Decision | None = None
    
    def review(self, quote: QuoteDraft) -> Decision:
        self.quote = quote
        self.on_review()
        if not self.event.wait(timeout=3600):  # Wait up to 1 hour
            now = datetime.now(timezone.utc)
            return Decision(
                action="reject",
                notes="approval timed out",
                decided_at=now
            )
        
        return self._decision or Decision(
            action="reject", notes="internal error", decided_at=datetime.now(timezone.utc)
        )
    
    def resolve(self, action: str, notes: str | None) -> bool:
        if action not in ("approve", "reject"):
            raise ValueError("Action must be 'approve' or 'reject'")
        
        if self.quote is None or self.event.is_set():
            return False
        
        decision = Decision(
            action=action,
            notes=notes if notes and notes.strip() else None,
            decided_at=datetime.now(timezone.utc)
        )
        
        self._decision = decision
        self.event.set()
        return True


@dataclass
class Submission:
    sid: str
    source: str
    created_at: datetime
    status: str
    stages: list[str]
    gate: WebGate
    result: RunResult | None = None
    error: str | None = None


SUBMISSIONS: dict[str, Submission] = {}
SUBMISSIONS_LOCK = threading.Lock()


def sub_view(sub: Submission) -> dict[str, Any]:
    """Convert a Submission to a view dictionary for templates."""
    quote = sub.gate.quote or (sub.result.quote if sub.result else None)
    
    company = quote.customer.company if quote and quote.customer else None
    quote_number = quote.quote_number if quote else None
    total_usd = f"{quote.total_usd:,}" if quote and hasattr(quote, 'total_usd') and quote.total_usd else None
    total_cny = f"{quote.total_cny:,}" if quote and hasattr(quote, 'total_cny') and quote.total_cny else None
    
    risk_flags = []
    if quote and hasattr(quote, 'risk_flags'):
        for flag in quote.risk_flags:
            risk_flags.append({
                "code": flag.code,
                "severity": flag.severity,
                "message_en": flag.message_en,
                "message_zh": flag.message_zh
            })
    
    artifacts = []
    if sub.result and sub.result.artifacts:
        for kind, path_str in sub.result.artifacts.items():
            path = Path(path_str)
            artifacts.append({
                "kind": kind,
                "run_id": path.parent.name,
                "filename": path.name
            })
    
    tokens = None
    if sub.result and sub.result.usage:
        total_tokens = 0
        for model_usage in sub.result.usage.values():
            total_tokens += model_usage.get('prompt_tokens', 0) + model_usage.get('completion_tokens', 0)
        tokens = total_tokens
    
    return {
        "sid": sub.sid,
        "source": sub.source,
        "status": sub.status,
        "created_at": sub.created_at.strftime("%H:%M:%S"),
        "stages": sub.stages,
        "company": company,
        "quote_number": quote_number,
        "total_usd": total_usd,
        "total_cny": total_cny,
        "risk_flags": risk_flags,
        "artifacts": artifacts,
        "tokens": tokens,
        "error": sub.error
    }




def _goto(url: str) -> HTMLResponse:
    """Client-side redirect: FC's fcapp.run system domain forbids 3xx responses."""
    return HTMLResponse(
        f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={url}">'
        f'</head><body><a href="{url}">Continue → {url}</a></body></html>'
    )

app = FastAPI(title="QuotePilot")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    with SUBMISSIONS_LOCK:
        submissions_list = list(SUBMISSIONS.values())
    
    # Sort by creation time, newest first
    submissions_list.sort(key=lambda x: x.created_at, reverse=True)
    
    # Get archived runs
    archived = []
    try:
        from quotepilot.web.runs_index import list_runs
        archived = list_runs(RUNS_DIR)
    except ImportError:
        pass  # If runs_index is not available, return empty list
    
    # Get sample files
    samples_dir = DATA_DIR / "samples"
    samples = []
    if samples_dir.exists():
        for file_path in samples_dir.iterdir():
            if file_path.suffix == ".txt":
                samples.append(file_path.name)
        samples.sort()
    
    context = {
        "request": request,
        "submissions": [sub_view(s) for s in submissions_list],
        "archived": archived,
        "samples": samples
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/sample/{name}")
async def get_sample(name: str):
    # Validate filename format
    if not re.match(r'^[A-Za-z0-9_]+\.txt$', name):
        raise HTTPException(status_code=404, detail="Sample not found")
    
    sample_path = DATA_DIR / "samples" / name
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample not found")
    
    content = sample_path.read_text(encoding='utf-8')
    return {"name": name, "text": content}


@app.post("/submit")
async def submit_email(email_text: str = Form(..., min_length=20)):
    email_text = email_text.strip()
    if len(email_text) < 20:
        raise HTTPException(status_code=422, detail="Email text too short")
    
    sid = uuid4().hex[:12]
    gate = WebGate(on_review=lambda: update_submission_status(sid, "awaiting_approval"))
    
    submission = Submission(
        sid=sid,
        source="web",
        created_at=datetime.now(timezone.utc),
        status="running",
        stages=[],
        gate=gate
    )
    
    with SUBMISSIONS_LOCK:
        SUBMISSIONS[sid] = submission
    
    # Start processing in a background thread
    def process_submission():
        try:
            def progress_callback(stage: str):
                with SUBMISSIONS_LOCK:
                    if sid in SUBMISSIONS:
                        SUBMISSIONS[sid].stages.append(stage)
            
            result = run_autopilot(
                raw_email=email_text,
                gate=gate,
                runs_dir=RUNS_DIR,
                source_name=f"web_{sid}",
                progress=progress_callback
            )
            
            with SUBMISSIONS_LOCK:
                if sid in SUBMISSIONS:
                    submission = SUBMISSIONS[sid]
                    submission.result = result
                    if result.decision.action == "approve":
                        submission.status = "approved"
                    else:
                        submission.status = "rejected"
        except Exception as e:
            with SUBMISSIONS_LOCK:
                if sid in SUBMISSIONS:
                    SUBMISSIONS[sid].status = "failed"
                    SUBMISSIONS[sid].error = str(e)
    
    thread = threading.Thread(target=process_submission, daemon=True)
    thread.start()
    
    return _goto(f"/s/{sid}")


def update_submission_status(sid: str, status: str):
    with SUBMISSIONS_LOCK:
        if sid in SUBMISSIONS:
            SUBMISSIONS[sid].status = status


@app.get("/s/{sid}", response_class=HTMLResponse)
async def get_submission(request: Request, sid: str):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    summary = None
    if submission.status == "awaiting_approval" and submission.gate.quote:
        summary = summarize(submission.gate.quote)
    
    context = {
        "request": request,
        "s": sub_view(submission),
        "summary": summary
    }
    return templates.TemplateResponse(request, "submission.html", context)


@app.get("/s/{sid}/state")
async def get_submission_state(sid: str):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    return {
        "status": submission.status,
        "stages": submission.stages
    }


@app.get("/s/{sid}/preview", response_class=HTMLResponse)
async def get_preview(sid: str):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    if not submission.gate.quote:
        raise HTTPException(status_code=404, detail="Quote not available yet")
    
    html_content = render_quote_html(submission.gate.quote)
    return HTMLResponse(content=html_content)


@app.post("/s/{sid}/decision")
async def make_decision(sid: str, action: str = Form(...), notes: str | None = Form(None)):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    
    # Check for blocking risk flags if approving
    if action == "approve" and submission.gate.quote:
        for flag in submission.gate.quote.risk_flags:
            if flag.severity == "block":
                raise HTTPException(status_code=409, detail="Cannot approve due to blocking risk flags")
    
    success = submission.gate.resolve(action, notes)
    if not success:
        raise HTTPException(status_code=409, detail="Decision could not be processed")
    
    return _goto(f"/s/{sid}")


@app.get("/artifacts/{run_id}/{filename}")
async def get_artifact(run_id: str, filename: str):
    # Validate run_id and filename formats
    if not re.match(r'^[0-9\-a-f]+$', run_id):
        raise HTTPException(status_code=404, detail="Invalid run ID")
    
    if not re.match(r'^[A-Za-z0-9._\-]+$', filename):
        raise HTTPException(status_code=404, detail="Invalid filename")
    
    # Check file extension
    allowed_extensions = {'.html', '.md', '.json', '.txt', '.jsonl'}
    if Path(filename).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=404, detail="Invalid file type")
    
    artifact_path = RUNS_DIR / run_id / filename
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(artifact_path)

```

## File 2: extend `tests/test_web.py` (emit COMPLETE updated file)

Add tests (existing tests must be preserved):
- `test_api_bootstrap`: GET /api/bootstrap → 200, has keys samples/submissions/archived, samples contains "inquiry_zh_1.txt"
- `test_api_submit_validation`: POST /api/submit with `{"email_text": "hi"}` → 422
- `test_api_unknown_submission`: GET /api/s/nope → 404; POST /api/s/nope/decision `{"action":"approve"}` → 404
- CORS: GET / with header `Origin: https://example.github.io` → response has `access-control-allow-origin: *`

Current tests file:

```python
import threading
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from quotepilot import config
from quotepilot.models import CoverLetters, Customer, FxRate, QuoteDraft, RiskFlag
from quotepilot.web.app import WebGate, app

client = TestClient(app)


def make_quote(severity="info"):
    return QuoteDraft(
        quote_number="LUQ-Q-TEST-0001",
        issue_date=date(2026, 7, 9),
        valid_until=date(2026, 8, 8),
        customer=Customer(contact_name="T", company="TestCo", email="t@x.cn"),
        lines=[],
        subtotal_usd=Decimal("0"),
        discount_usd=Decimal("0"),
        total_usd=Decimal("0"),
        total_cny=Decimal("0"),
        fx=FxRate(rate=Decimal("7.2"), source="test", as_of="2026-07-09"),
        cover=CoverLetters(
            cover_letter_en="e", cover_letter_zh="z", answers_en="", answers_zh=""
        ),
        payment_terms_en="p",
        payment_terms_zh="p",
        legal_en="l",
        legal_zh="l",
        risk_flags=[
            RiskFlag(code="T", severity=severity, message_en="m", message_zh="m")
        ],
    )


def test_dashboard_renders():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "QuotePilot" in resp.text


def test_sample_endpoint():
    resp = client.get("/sample/inquiry_zh_1.txt")
    assert resp.status_code == 200
    assert "RentalNote" in resp.json()["text"]


def test_sample_rejects_bad_names():
    assert client.get("/sample/../secrets.txt").status_code in (404, 422)
    assert client.get("/sample/evil.py").status_code == 404


def test_artifacts_rejects_traversal():
    assert client.get("/artifacts/../x/quote.html").status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/../../.env").status_code in (404, 422)
    assert client.get("/artifacts/20260101-000000-aa/x.py").status_code == 404


def test_unknown_submission_404():
    assert client.get("/s/nope").status_code == 404
    assert client.post("/s/nope/decision", data={"action": "approve"}).status_code == 404


def test_webgate_approve_roundtrip():
    reviewed = threading.Event()
    gate = WebGate(on_review=reviewed.set)
    out = {}

    def worker():
        out["decision"] = gate.review(make_quote())

    t = threading.Thread(target=worker)
    t.start()
    assert reviewed.wait(5)
    assert gate.resolve("approve", "ok") is True
    t.join(5)
    assert out["decision"].action == "approve"
    assert out["decision"].notes == "ok"
    # second resolve is a no-op
    assert gate.resolve("reject", None) is False

```

## Files to output
1. `src/quotepilot/web/app.py` (complete)
2. `tests/test_web.py` (complete)

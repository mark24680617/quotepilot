from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

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

    # Editable detail (raw numeric strings for the line-item editor).
    lines = None
    customer = None
    cover = None
    if quote:
        lines = [
            {
                "sku": l.sku, "name_en": l.name_en, "name_zh": l.name_zh,
                "unit": l.unit, "unit_zh": l.unit_zh,
                "quantity": str(l.quantity), "unit_price_usd": str(l.unit_price_usd),
                "discount_pct": str(l.discount_pct), "line_total_usd": str(l.line_total_usd),
            }
            for l in quote.lines
        ]
        customer = {"contact_name": quote.customer.contact_name,
                    "company": quote.customer.company, "email": quote.customer.email}
        cover = {"cover_letter_en": quote.cover.cover_letter_en,
                 "cover_letter_zh": quote.cover.cover_letter_zh,
                 "answers_en": quote.cover.answers_en, "answers_zh": quote.cover.answers_zh}

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
        "error": sub.error,
        "lines": lines,
        "customer": customer,
        "cover": cover,
    }


def _gather_dashboard_data():
    """Gather data for both dashboard and API bootstrap endpoint"""
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
    
    return {
        "submissions": [sub_view(s) for s in submissions_list],
        "archived": [entry.model_dump() for entry in archived],
        "samples": samples
    }


def _start_submission(email_text: str) -> str:
    """Start a new submission - shared between web form and API"""
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
    
    return sid


def _goto(url: str) -> HTMLResponse:
    """Client-side redirect: FC's fcapp.run system domain forbids 3xx responses."""
    return HTMLResponse(
        f'<!DOCTYPE html><html><head><meta http-equiv="refresh" content="0;url={url}">'
        f'</head><body><a href="{url}">Continue → {url}</a></body></html>'
    )

app = FastAPI(title="QuotePilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # anonymous public demo API — no cookies/credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

from quotepilot.web.profile_api import router as profile_router  # noqa: E402

app.include_router(profile_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    data = _gather_dashboard_data()
    
    context = {
        "request": request,
        "submissions": data["submissions"],
        "archived": data["archived"],
        "samples": data["samples"]
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.get("/api/bootstrap")
async def api_bootstrap():
    data = _gather_dashboard_data()
    return {
        "samples": data["samples"],
        "submissions": data["submissions"],
        "archived": data["archived"]
    }


class SubmitRequest(BaseModel):
    email_text: str


@app.post("/api/submit")
async def api_submit(request: SubmitRequest):
    email_text = request.email_text.strip()
    if len(email_text) < 20:
        raise HTTPException(status_code=422, detail="Email text too short")
    
    sid = _start_submission(email_text)
    return {"sid": sid}


@app.get("/api/s/{sid}")
async def api_get_submission(sid: str):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    summary = None
    if submission.status == "awaiting_approval" and submission.gate.quote:
        summary = summarize(submission.gate.quote)
    
    return {
        "s": sub_view(submission),
        "summary": summary
    }


class EditRequest(BaseModel):
    lines: list[dict] | None = None
    customer: dict | None = None
    cover: dict | None = None
    extra_notes_en: list[str] | None = None
    extra_notes_zh: list[str] | None = None


@app.post("/api/s/{sid}/edit")
async def api_edit_quote(sid: str, request: EditRequest):
    """Re-price the quote from human line-item edits (Decimal math, server-side)."""
    from quotepilot import core

    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    gate = submission.gate
    if submission.status != "awaiting_approval" or gate.quote is None:
        raise HTTPException(status_code=409, detail="Quote is not open for editing")

    edits = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        new_quote = core.reprice_quote(gate.quote, edits)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not reprice: {e}")

    gate.quote = new_quote  # the approval + preview now use the edited quote
    return {"ok": True, "s": sub_view(submission), "summary": summarize(new_quote)}


class DecisionRequest(BaseModel):
    action: str
    notes: str | None = None


@app.post("/api/s/{sid}/decision")
async def api_make_decision(sid: str, request: DecisionRequest):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    if request.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    
    # Check for blocking risk flags if approving
    if request.action == "approve" and submission.gate.quote:
        for flag in submission.gate.quote.risk_flags:
            if flag.severity == "block":
                raise HTTPException(status_code=409, detail="Cannot approve due to blocking risk flags")
    
    success = submission.gate.resolve(request.action, request.notes)
    if not success:
        raise HTTPException(status_code=409, detail="Decision could not be processed")
    
    # Read the status after resolve
    with SUBMISSIONS_LOCK:
        submission_after_resolve = SUBMISSIONS.get(sid)
        status_after_resolve = submission_after_resolve.status if submission_after_resolve else "unknown"
    
    return {
        "ok": True,
        "status": status_after_resolve
    }


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
    
    sid = _start_submission(email_text)
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

from __future__ import annotations

import logging
import os
import re
import secrets
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
from pydantic import BaseModel, Field

from quotepilot.config import DATA_DIR, RUNS_DIR
from quotepilot.hitl import summarize
from quotepilot.models import Decision, QuoteDraft, RunResult
from quotepilot.orchestrator import run_autopilot
from quotepilot.stages.render import render_quote_html
from quotepilot.web import auth, guard

logger = logging.getLogger("quotepilot.web")

# Origins allowed to call this API from a browser (defense-in-depth; a curl
# attacker ignores CORS, which is why the rate-limit/daily-cap above matter).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "QP_ALLOWED_ORIGINS",
        "https://mark24680617.github.io,http://localhost:8123,http://127.0.0.1:8123",
    ).split(",")
    if o.strip()
]


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
    owner_user: str = ""  # the logged-in user who started this run
    result: RunResult | None = None
    error: str | None = None


SUBMISSIONS: dict[str, Submission] = {}
SUBMISSIONS_LOCK = threading.Lock()
# Bounded worker pool: cap concurrent pipelines so a burst can't launch
# unbounded qwen-max calls or exhaust threads.
_INFLIGHT = threading.BoundedSemaphore(guard.MAX_INFLIGHT)


def _require_owner(request: Request, sub: Submission) -> None:
    """Only the run's owner (or admin) may edit/approve/reject it."""
    user = auth.current_user(request)
    if user != sub.owner_user and user != auth.ADMIN_USER:
        raise HTTPException(status_code=403, detail="You can only edit or decide your own runs.")


def _evict_old_submissions() -> None:
    """Keep the in-memory map bounded (called under SUBMISSIONS_LOCK)."""
    if len(SUBMISSIONS) <= guard.MAX_SUBMISSIONS:
        return
    for sid in sorted(SUBMISSIONS, key=lambda s: SUBMISSIONS[s].created_at)[
        : len(SUBMISSIONS) - guard.MAX_SUBMISSIONS
    ]:
        SUBMISSIONS.pop(sid, None)


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


def _gather_dashboard_data(user: str | None = None):
    """Gather data for the API bootstrap endpoint, scoped to one user's runs."""
    with SUBMISSIONS_LOCK:
        submissions_list = [
            s for s in SUBMISSIONS.values()
            if user is None or s.owner_user == user
        ]

    # Sort by creation time, newest first
    submissions_list.sort(key=lambda x: x.created_at, reverse=True)

    # Archived runs (from disk) aren't user-tagged; only admin sees them.
    archived = []
    if user is None or user == auth.ADMIN_USER:
        try:
            from quotepilot.web.runs_index import list_runs
            archived = list_runs(RUNS_DIR)
        except ImportError:
            pass

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


def _start_submission(email_text: str, user: str) -> str:
    """Start a new submission for `user`. Returns the sid.

    The daily global cap is checked BEFORE any model call; if a worker slot
    isn't free we refuse rather than pile up threads.
    """
    from quotepilot.profile import load_profile

    guard.daily_gate("submit")  # 429 if the demo's daily model budget is spent
    if not _INFLIGHT.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Server busy — too many runs in flight. Try again shortly.")

    profile = load_profile(user)  # the seller runs against THEIR own company profile
    sid = uuid4().hex[:12]
    gate = WebGate(on_review=lambda: update_submission_status(sid, "awaiting_approval"))

    submission = Submission(
        sid=sid, source="web", created_at=datetime.now(timezone.utc),
        status="running", stages=[], gate=gate, owner_user=user,
    )
    with SUBMISSIONS_LOCK:
        SUBMISSIONS[sid] = submission
        _evict_old_submissions()

    def process_submission():
        try:
            def progress_callback(stage: str):
                with SUBMISSIONS_LOCK:
                    if sid in SUBMISSIONS:
                        SUBMISSIONS[sid].stages.append(stage)

            result = run_autopilot(
                raw_email=email_text, gate=gate, runs_dir=RUNS_DIR,
                source_name=f"web_{sid}", progress=progress_callback, profile=profile,
            )
            with SUBMISSIONS_LOCK:
                if sid in SUBMISSIONS:
                    submission = SUBMISSIONS[sid]
                    submission.result = result
                    submission.status = "approved" if result.decision.action == "approve" else "rejected"
        except Exception as e:
            logger.exception("submission %s failed", sid)
            with SUBMISSIONS_LOCK:
                if sid in SUBMISSIONS:
                    SUBMISSIONS[sid].status = "failed"
                    SUBMISSIONS[sid].error = "Pipeline error"  # generic; details in server log
        finally:
            _INFLIGHT.release()

    threading.Thread(target=process_submission, daemon=True).start()
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
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,       # anonymous, no cookies — never reflect+credentials
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-QP-Owner-Token"],
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    for k, v in guard.SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


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


class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth")
async def api_auth(request: Request, body: AuthRequest):
    """Login or auto-signup: unknown username creates an account."""
    guard.rate_limit(request, "auth")
    token = auth.authenticate(body.username, body.password)
    return {"token": token, "username": body.username.strip()}


@app.post("/api/logout")
async def api_logout(request: Request):
    auth.logout(request.headers.get("authorization", "").removeprefix("Bearer ").strip()
                or request.headers.get("x-qp-token", "").strip())
    return {"ok": True}


@app.get("/api/bootstrap")
async def api_bootstrap(request: Request):
    user = auth.current_user(request)
    data = _gather_dashboard_data(user)
    return {
        "user": user,
        "samples": data["samples"],
        "submissions": data["submissions"],
        "archived": data["archived"],
    }


class SubmitRequest(BaseModel):
    email_text: str = Field(min_length=20, max_length=guard.MAX_EMAIL_CHARS)


@app.post("/api/submit")
async def api_submit(request: Request, body: SubmitRequest):
    user = auth.current_user(request)
    guard.rate_limit(request, "submit")
    email_text = body.email_text.strip()
    if len(email_text) < 20:
        raise HTTPException(status_code=422, detail="Email text too short")
    sid = _start_submission(email_text, user)
    return {"sid": sid}


@app.get("/api/s/{sid}")
async def api_get_submission(sid: str, request: Request):
    user = auth.current_user(request)
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.owner_user != user and user != auth.ADMIN_USER:
        raise HTTPException(status_code=403, detail="Not your run")

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
async def api_edit_quote(sid: str, request: Request, body: EditRequest):
    """Re-price the quote from human line-item edits (Decimal math, server-side)."""
    from quotepilot import core

    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    _require_owner(request, submission)
    gate = submission.gate
    if submission.status != "awaiting_approval" or gate.quote is None:
        raise HTTPException(status_code=409, detail="Quote is not open for editing")

    edits = {k: v for k, v in body.model_dump().items() if v is not None}
    lines = edits.get("lines")
    if isinstance(lines, list) and len(lines) > guard.MAX_LINE_ITEMS:
        raise HTTPException(status_code=422, detail=f"Too many line items (max {guard.MAX_LINE_ITEMS})")
    try:
        new_quote = core.reprice_quote(gate.quote, edits)
    except Exception as e:
        logger.warning("reprice failed for %s: %s", sid, e)
        raise HTTPException(status_code=422, detail="Could not reprice quote")

    gate.quote = new_quote  # the approval + preview now use the edited quote
    return {"ok": True, "s": sub_view(submission), "summary": summarize(new_quote)}


class DecisionRequest(BaseModel):
    action: str
    notes: str | None = None


@app.post("/api/s/{sid}/decision")
async def api_make_decision(sid: str, request: Request, body: DecisionRequest):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    _require_owner(request, submission)

    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")

    # Check for blocking risk flags if approving
    if body.action == "approve" and submission.gate.quote:
        for flag in submission.gate.quote.risk_flags:
            if flag.severity == "block":
                raise HTTPException(status_code=409, detail="Cannot approve due to blocking risk flags")
    
    success = submission.gate.resolve(body.action, body.notes)
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
async def submit_email(request: Request, email_text: str = Form(..., min_length=20, max_length=guard.MAX_EMAIL_CHARS)):
    user = auth.current_user(request)
    guard.rate_limit(request, "submit")
    email_text = email_text.strip()
    if len(email_text) < 20:
        raise HTTPException(status_code=422, detail="Email text too short")
    sid = _start_submission(email_text, user)
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
async def get_submission_state(sid: str, request: Request):
    user = auth.current_user(request)
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.owner_user != user and user != auth.ADMIN_USER:
        raise HTTPException(status_code=403, detail="Not your run")

    return {"status": submission.status, "stages": submission.stages}


@app.get("/s/{sid}/preview", response_class=HTMLResponse)
async def get_preview(sid: str, request: Request):
    user = auth.current_user(request)
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    if submission.owner_user != user and user != auth.ADMIN_USER:
        raise HTTPException(status_code=403, detail="Not your run")
    if not submission.gate.quote:
        raise HTTPException(status_code=404, detail="Quote not available yet")

    html_content = render_quote_html(submission.gate.quote)
    return HTMLResponse(content=html_content)


@app.post("/s/{sid}/decision")
async def make_decision(request: Request, sid: str, action: str = Form(...), notes: str | None = Form(None)):
    with SUBMISSIONS_LOCK:
        submission = SUBMISSIONS.get(sid)

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    _require_owner(request, submission)

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
async def get_artifact(run_id: str, filename: str, request: Request):
    auth.current_user(request)  # any signed-in user
    # Validate run_id and filename formats
    if not re.match(r'^[0-9\-a-f]+$', run_id):
        raise HTTPException(status_code=404, detail="Invalid run ID")
    
    if not re.match(r'^[A-Za-z0-9._\-]+$', filename):
        raise HTTPException(status_code=404, detail="Invalid filename")
    
    # Check file extension
    allowed_extensions = {'.html', '.md', '.json', '.txt', '.jsonl'}
    if Path(filename).suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=404, detail="Invalid file type")
    
    runs_root = RUNS_DIR.resolve()
    artifact_path = (runs_root / run_id / filename).resolve()
    # Containment guard (defense-in-depth on top of the regex validation).
    if runs_root not in artifact_path.parents or not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")

    from fastapi.responses import FileResponse
    # Serve untrusted artifact bytes as an attachment so a browser never
    # renders/executes them inline at this origin.
    return FileResponse(artifact_path, headers={"Content-Disposition": "attachment"})

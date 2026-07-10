# Task T1: FastAPI approval dashboard backend for QuotePilot

Build `src/quotepilot/web/__init__.py` (empty) and `src/quotepilot/web/app.py` —
a FastAPI app that lets a human submit inquiry emails, watch the autopilot
pipeline progress, approve/reject the drafted quote, and browse artifacts.

## Existing project interfaces (import these; do NOT redefine)

```python
# quotepilot.config
RUNS_DIR: Path          # runs output root
DATA_DIR: Path          # data dir; samples live in DATA_DIR / "samples"

# quotepilot.models (pydantic v2)
class Decision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    notes: Optional[str]
    decided_at: datetime

class QuoteDraft(BaseModel):
    quote_number: str
    customer: Customer            # .company .contact_name .email (str)
    total_usd: Decimal
    total_cny: Decimal
    risk_flags: list[RiskFlag]    # .code .severity("info"|"warn"|"block") .message_en .message_zh
    # ... more fields; treat as opaque otherwise

class RunResult(BaseModel):
    run_id: str
    decision: Decision
    quote: QuoteDraft
    artifacts: dict[str, str]     # kind -> ABSOLUTE file path
    usage: dict[str, dict[str, int]]  # model -> {prompt_tokens, completion_tokens, calls}

# quotepilot.hitl
def summarize(quote: QuoteDraft) -> str   # plain-text summary block

# quotepilot.orchestrator
def run_autopilot(
    raw_email: str,
    gate,                          # object with .review(quote) -> Decision
    runs_dir: Path | None = None,
    source_name: str = "stdin",
    progress: Optional[Callable[[str], None]] = None,  # called with stage name
) -> RunResult                     # raises on failure

# quotepilot.stages.render
def render_quote_html(quote: QuoteDraft) -> str
```

Pipeline stage names arriving via `progress`, in order:
`intake, fx, pricing, risk_rules, risk_llm_sweep, drafting`.

## Required components in app.py

### WebGate
```python
class WebGate:
    quote: QuoteDraft | None
    def __init__(self, on_review: Callable[[], None]) -> None: ...
    def review(self, quote: QuoteDraft) -> Decision:
        # store quote, call on_review(), then block on a threading.Event
        # for up to 3600s. On timeout return Decision(action="reject",
        # notes="approval timed out", decided_at=now-utc).
    def resolve(self, action: str, notes: str | None) -> bool:
        # build Decision (action must be "approve" or "reject"; notes None if
        # blank), hand to the waiting review(), set the event.
        # Return False if no review is pending or already resolved.
```

### Submission registry
```python
@dataclass
class Submission:
    sid: str                      # uuid4 hex[:12]
    source: str                   # e.g. "web"
    created_at: datetime
    status: str                   # running|awaiting_approval|approved|rejected|failed
    stages: list[str]
    gate: WebGate
    result: RunResult | None = None
    error: str | None = None
```
Module-level `SUBMISSIONS: dict[str, Submission]` guarded by a
`threading.Lock` for insertion/lookup. Pipeline runs in a daemon
`threading.Thread` per submission:
- progress callback appends stage names to `stages`
- gate's on_review sets status to "awaiting_approval"
- on completion: status = "approved" if result.decision.action == "approve"
  else "rejected"; store result
- on exception: status = "failed", error = str(exc)

Blocking `block`-severity flags are enforced downstream — but the decision
endpoint must refuse `action=approve` with HTTP 409 if
`any(f.severity == "block" for f in gate.quote.risk_flags)`.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| GET | `/` | render `dashboard.html` |
| GET | `/sample/{name}` | JSON `{"name": ..., "text": ...}` from `DATA_DIR/"samples"/name`; validate name against `^[A-Za-z0-9_]+\.txt$`, 404 if missing |
| POST | `/submit` | form field `email_text` (min length 20 after strip, else 422); create submission, start thread, 303 redirect to `/s/{sid}` |
| GET | `/s/{sid}` | render `submission.html`; 404 unknown sid |
| GET | `/s/{sid}/state` | JSON `{"status": ..., "stages": [...]}` |
| GET | `/s/{sid}/preview` | `HTMLResponse(render_quote_html(gate.quote))`; 404 if gate.quote is None |
| POST | `/s/{sid}/decision` | form fields `action` ("approve"/"reject"), `notes` (optional); call gate.resolve; 409 if resolve returns False or approve-on-block; 303 back to `/s/{sid}` |
| GET | `/artifacts/{run_id}/{filename}` | FileResponse from `RUNS_DIR/run_id/filename`; validate `run_id` `^[0-9\-a-f]+$` and `filename` `^[A-Za-z0-9._\-]+$`, suffix in {.html,.md,.json,.txt,.jsonl}; 404 otherwise |

App must import cleanly without QWEN_API_KEY set (no LLM client at import
time — the project already guarantees this; just don't call llm code at
module import).

## Template contexts (templates are written by another task — match EXACTLY)

Templates live in `src/quotepilot/web/templates`; use
`fastapi.templating.Jinja2Templates(directory=str(Path(__file__).parent / "templates"))`.

`dashboard.html` context:
```python
{"request": request,
 "submissions": [sub_view(s) for s in ...newest first...],
 "archived": list_runs(RUNS_DIR),      # from quotepilot.web.runs_index (another task); import inside the route and wrap in try/except -> [] so the app still works if absent
 "samples": sorted 3 sample filenames from DATA_DIR/"samples"}
```

`submission.html` context:
```python
{"request": request, "s": sub_view(sub),
 "summary": summarize(sub.gate.quote) if status=="awaiting_approval" else None}
```

`sub_view(sub)` returns a plain dict:
```python
{"sid", "source", "status", "created_at",          # created_at: "%H:%M:%S" string
 "stages": list[str],
 "company": quote.customer.company or None,        # None until quote exists (use gate.quote or result.quote)
 "quote_number": ... or None,
 "total_usd": f"{quote.total_usd:,}" or None,
 "total_cny": f"{quote.total_cny:,}" or None,
 "risk_flags": [{"code","severity","message_en","message_zh"}] or [],
 "artifacts": [{"kind", "run_id", "filename"}],    # from result.artifacts paths: run_id = Path(p).parent.name, filename = Path(p).name
 "tokens": total prompt+completion across result.usage or None,
 "error": sub.error}
```

## Files to output
1. `src/quotepilot/web/__init__.py` — empty module docstring only.
2. `src/quotepilot/web/app.py` — everything above. `app = FastAPI(title="QuotePilot")`.

# Task T4: AgentScope 2.0 agent path for QuotePilot

Build `src/quotepilot/agent_runner.py` — an alternative entry point where an
**AgentScope 2.0** agent drives the quote pipeline as tools, with the
finalize step gated by AgentScope's native permission system
(`RequireUserConfirmEvent` = our human-in-the-loop pause).

AgentScope **2.0.4** is installed. The API below was verified against the
installed package by introspection — use it EXACTLY; do not rely on
AgentScope 1.x knowledge (`sequential_pipeline`, `agentscope.init` etc. no
longer exist).

## Verified AgentScope 2.0.4 API

```python
from agentscope.agent import Agent
from agentscope.credential import DashScopeCredential   # pydantic model: DashScopeCredential(api_key=<str>, base_url=<str>)
from agentscope.model import DashScopeChatModel         # DashScopeChatModel(credential=..., model=<str>)
from agentscope.tool import Toolkit, FunctionTool       # Toolkit(tools=[FunctionTool(func), ...])
from agentscope.state import AgentState                 # AgentState(permission_context=...)
from agentscope.permission import (
    PermissionBehavior, PermissionContext, PermissionMode, PermissionRule,
)
# PermissionContext(mode=PermissionMode.DEFAULT,
#                   allow_rules={"tool_name": [PermissionRule(...)]})
# allow_rules: dict[str, list[PermissionRule]]
# PermissionRule fields: tool_name, rule_content, behavior, source
from agentscope.event import (
    ConfirmResult,               # ConfirmResult(confirmed: bool, tool_call: ToolCallBlock, rules=None)
    ReplyEndEvent,
    RequireUserConfirmEvent,     # fields: id, created_at, metadata, type, reply_id, tool_calls
    TextBlockDeltaEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    UserConfirmResultEvent,      # UserConfirmResultEvent(reply_id=..., confirm_results=[ConfirmResult, ...])
)
from agentscope.message import Msg, UserMsg

# Agent(name=..., system_prompt=..., model=..., toolkit=..., state=AgentState(...))
# reply_stream(inputs: Msg | list[Msg] | UserConfirmResultEvent | ...) -> AsyncGenerator[events]
# reply(inputs) -> Msg
# FunctionTool(func, name=None, description=None, is_read_only=False)
#   -> schema auto-extracted from the function signature + docstring;
#      plain return values are normalized to tool chunks automatically.
```

Event objects for tool calls: `ToolCallStartEvent` carries the tool call
info; use `getattr(ev, 'tool_call', None)` defensively when printing (the
exact attribute layout may vary — degrade to printing the event type name).
`RequireUserConfirmEvent.tool_calls` is a list of tool-call blocks; each
block has a `.name` attribute (fall back to `block.get("name")` if it's a
dict).

## Project interfaces to reuse (already implemented)

```python
from quotepilot import config           # config.QWEN_API_KEY, config.QWEN_BASE_URL,
                                        # config.PLANNER_MODEL ("qwen-max"), config.RUNS_DIR
from quotepilot import core, llm
core.assemble_quote_draft(raw_email: str, usage: llm.UsageTracker | None = None, on_stage=None)
    -> tuple[QuoteDraft, Inquiry]       # runs the full pricing pipeline (LLM calls inside)
core.render_artifacts(quote: QuoteDraft, run_dir: Path) -> dict[str, str]
from quotepilot.hitl import summarize   # summarize(quote) -> str
```

## Required design

Module-level store: `QUOTES: dict[str, QuoteDraft] = {}`.

### Tool functions (plain Python functions wrapped in FunctionTool)

```python
def assemble_quote(email_text: str) -> str:
    """Run the QuotePilot pricing pipeline on a raw inquiry email (English or
    Chinese) and assemble a bilingual quote draft.

    Args:
        email_text: The complete raw inquiry email text.
    """
    # call core.assemble_quote_draft, store draft in QUOTES by quote_number,
    # return summarize(quote) plus a final line:
    # "Draft stored. To render final artifacts call finalize_quote with quote_number=<...>"

def finalize_quote(quote_number: str) -> str:
    """Render the final quote artifacts (HTML quote document + reply email)
    for a previously assembled quote draft. Requires human approval.

    Args:
        quote_number: The quote number returned by assemble_quote.
    """
    # look up QUOTES (error string if unknown), refuse with an explanatory
    # string if any risk flag has severity "block",
    # else core.render_artifacts(quote, config.RUNS_DIR / f"agent-{quote_number}")
    # and return the artifact paths, one per line.
```

### Permission wiring

- `PermissionContext(mode=PermissionMode.DEFAULT, allow_rules={"assemble_quote": [PermissionRule(tool_name="assemble_quote", rule_content="*", behavior=PermissionBehavior.ALLOW, source="userSettings")]})`
- `finalize_quote` gets NO rule → under DEFAULT mode the framework pauses and
  emits `RequireUserConfirmEvent` before executing it. That pause is our HITL.

### Runner

```python
async def run_agent(email_text: str, auto_confirm: bool = False) -> str: ...
def main_sync(email_text: str, auto_confirm: bool = False) -> str:
    # asyncio.run wrapper
```

run_agent flow:
1. Build credential/model (`DashScopeChatModel(credential=DashScopeCredential(api_key=config.QWEN_API_KEY, base_url=config.QWEN_BASE_URL), model=config.PLANNER_MODEL)`), toolkit, agent.
   System prompt: the agent is QuotePilot's autopilot orchestrator for
   LUQ LABS; given a raw inquiry email it MUST call assemble_quote exactly
   once, review the returned summary, then call finalize_quote with the
   returned quote number; afterwards reply with a short completion report
   (quote number, total, artifact paths). It must not invent prices.
2. `inputs = UserMsg(name="user", content=email_text)` (if UserMsg requires
   different args, fall back to `Msg(name="user", content=..., role="user")`).
3. Loop:
   ```python
   pending = None
   async for ev in agent.reply_stream(inputs):
       # print progress lines: tool call starts ("→ tool: <name>"),
       # streamed text deltas, tool results ("✓ tool finished")
       if isinstance(ev, RequireUserConfirmEvent):
           pending = ev
   if pending:
       results = []
       for tc in pending.tool_calls:
           name = getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else "?")
           if name == "finalize_quote" and not auto_confirm:
               ans = input(f"\n⏸  Human approval required for {name} — approve? [y/N] ")
               ok = ans.strip().lower() in ("y", "yes")
           else:
               ok = True   # auto-confirm everything else (and demo mode)
           results.append(ConfirmResult(confirmed=ok, tool_call=tc))
       inputs = UserConfirmResultEvent(reply_id=pending.reply_id, confirm_results=results)
       continue the loop (while True around the async-for)
   else:
       break
   ```
4. Return the final assistant text (accumulate TextBlockDeltaEvent contents
   from the last reply; also capture `agent.reply`'s final Msg content if the
   stream API makes that easier — either is fine as long as the returned
   string contains the completion report).

Print user-facing progress with flush=True. Import agentscope lazily INSIDE
functions so `import quotepilot.agent_runner` works even where agentscope is
not installed (raise a clear RuntimeError from main_sync if it is missing).

## Also modify (emit the complete updated file)

`src/quotepilot/cli.py` — add subcommand:
```
agent_p = sub.add_parser("agent", help="Run via AgentScope 2.0 agent (HITL through permission events)")
agent_p.add_argument("file", type=Path, help="Raw inquiry email text file")
agent_p.add_argument("--yes", action="store_true", help="Auto-confirm the approval gate (demo)")
```
dispatching to `from .agent_runner import main_sync; print(main_sync(path.read_text(encoding='utf-8'), auto_confirm=args.yes))`.

Current cli.py content to modify:

```python
"""CLI: `quotepilot run <email files...> [--auto-approve]`"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config
from .hitl import AutoApproveGate, CLIGate
from .orchestrator import run_autopilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="quotepilot",
        description="Email-to-quote autopilot agent (Qwen Cloud Hackathon, Track 4)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the autopilot on inquiry email file(s)")
    run_p.add_argument("files", nargs="+", type=Path, help="Raw inquiry email text files")
    run_p.add_argument(
        "--auto-approve",
        action="store_true",
        help="Skip interactive approval (demo/CI); blocking flags still reject",
    )
    run_p.add_argument("--out", type=Path, default=None, help="Runs output dir")

    web_p = sub.add_parser("web", help="Launch the approval dashboard (FastAPI)")
    web_p.add_argument("--host", default="0.0.0.0")
    web_p.add_argument("--port", type=int, default=9000)

    args = parser.parse_args(argv)

    if args.command == "web":
        import uvicorn

        uvicorn.run("quotepilot.web.app:app", host=args.host, port=args.port)
        return 0

    gate = AutoApproveGate() if args.auto_approve else CLIGate()
    failures = 0
    for path in args.files:
        print(f"\n=== QuotePilot run: {path.name} " + "=" * 40)
        raw = path.read_text(encoding="utf-8")
        try:
            result = run_autopilot(raw, gate, runs_dir=args.out, source_name=path.name)
        except Exception as err:  # surface, keep batch going
            print(f"✗ run failed: {err}", file=sys.stderr)
            failures += 1
            continue
        print(f"\nDecision: {result.decision.action.upper()}"
              + (f" — {result.decision.notes}" if result.decision.notes else ""))
        for kind, apath in result.artifacts.items():
            print(f"  {kind:<12} {apath}")
        tokens = sum(
            u["prompt_tokens"] + u["completion_tokens"] for u in result.usage.values()
        )
        print(f"  tokens       {tokens:,} across {len(result.usage)} model(s): "
              + ", ".join(f"{m} ({u['calls']} calls)" for m, u in result.usage.items()))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

```

## Files to output
1. `src/quotepilot/agent_runner.py`
2. `src/quotepilot/cli.py` (complete updated file)

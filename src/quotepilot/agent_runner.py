"""AgentScope 2.0 agent runner for QuotePilot."""

import asyncio
from typing import Dict

from . import config, core
from .hitl import summarize
from .models import QuoteDraft

# Module-level store for quotes
QUOTES: Dict[str, QuoteDraft] = {}


def assemble_quote(email_text: str) -> str:
    """Run the QuotePilot pricing pipeline on a raw inquiry email (English or
    Chinese) and assemble a bilingual quote draft.

    Args:
        email_text: The complete raw inquiry email text.
    """
    global QUOTES
    
    draft, inquiry = core.assemble_quote_draft(email_text)
    
    # Store the draft by quote number
    QUOTES[draft.quote_number] = draft
    
    summary = summarize(draft)
    return f"{summary}\nDraft stored. To render final artifacts call finalize_quote with quote_number={draft.quote_number}"


def finalize_quote(quote_number: str) -> str:
    """Render the final quote artifacts (HTML quote document + reply email)
    for a previously assembled quote draft. Requires human approval.

    Args:
        quote_number: The quote number returned by assemble_quote.
    """
    global QUOTES
    
    if quote_number not in QUOTES:
        return f"Error: Unknown quote number '{quote_number}'"
    
    quote = QUOTES[quote_number]
    
    # Check for blocking risk flags
    for risk_flag in quote.risk_flags:
        if risk_flag.severity == "block":
            return f"Refused: blocking risk flag [{risk_flag.code}] {risk_flag.message_en}"
    
    # Render artifacts
    artifacts = core.render_artifacts(quote, config.RUNS_DIR / f"agent-{quote_number}")
    
    # Format artifact paths as one per line
    result_lines = []
    for kind, path in artifacts.items():
        result_lines.append(f"{kind}: {path}")
    
    return "\n".join(result_lines)


async def run_agent(email_text: str, auto_confirm: bool = False) -> str:
    """Run the QuotePilot agent using AgentScope 2.0."""
    try:
        from agentscope.agent import Agent
        from agentscope.credential import DashScopeCredential
        from agentscope.model import DashScopeChatModel
        from agentscope.tool import Toolkit, FunctionTool
        from agentscope.state import AgentState
        from agentscope.permission import (
            PermissionBehavior, PermissionContext, PermissionMode, PermissionRule,
        )
        from agentscope.event import (
            ConfirmResult,
            ReplyEndEvent,
            RequireUserConfirmEvent,
            TextBlockDeltaEvent,
            ToolCallStartEvent,
            ToolResultEndEvent,
            UserConfirmResultEvent,
        )
        from agentscope.message import UserMsg
    except ImportError as e:
        raise RuntimeError("agentscope is not installed. Please install it to use this feature.") from e

    # Create credential and model
    credential = DashScopeCredential(
        api_key=config.QWEN_API_KEY,
        base_url=config.QWEN_BASE_URL,
    )
    model = DashScopeChatModel(
        credential=credential,
        model=config.PLANNER_MODEL,
    )

    # Create tools
    assemble_tool = FunctionTool(func=assemble_quote)
    finalize_tool = FunctionTool(func=finalize_quote)

    # Create toolkit
    toolkit = Toolkit(tools=[assemble_tool, finalize_tool])

    # Create permission context
    allow_assemble_rule = PermissionRule(
        tool_name="assemble_quote",
        rule_content="*",
        behavior=PermissionBehavior.ALLOW,
        source="userSettings"
    )
    permission_context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        allow_rules={
            "assemble_quote": [allow_assemble_rule]
        }
    )

    # Create agent
    agent = Agent(
        name="QuotePilotAgent",
        system_prompt=(
            "You are QuotePilot's autopilot orchestrator for LUQ LABS. "
            "Given a raw inquiry email you MUST call assemble_quote exactly once, "
            "review the returned summary, then call finalize_quote with the "
            "returned quote number. Afterwards reply with a short completion report "
            "(quote number, total, artifact paths). You must not invent prices."
        ),
        model=model,
        toolkit=toolkit,
        state=AgentState(permission_context=permission_context),
    )

    # Prepare initial input
    inputs = UserMsg(name="user", content=email_text)

    # Variables to accumulate final response
    final_response = ""
    pending = None

    while True:
        # Reset final_response for each loop iteration
        final_response = ""
        
        async for ev in agent.reply_stream(inputs):
            if isinstance(ev, ToolCallStartEvent):
                print(f"→ tool: {ev.tool_call_name}", flush=True)
            elif isinstance(ev, TextBlockDeltaEvent):
                if ev.delta:
                    print(ev.delta, end="", flush=True)
                    final_response += ev.delta
            elif isinstance(ev, ToolResultEndEvent):
                print("✓ tool finished", flush=True)
            elif isinstance(ev, RequireUserConfirmEvent):
                pending = ev
        
        print(flush=True)
        if pending:
            results = []
            for tc in pending.tool_calls:
                name = getattr(tc, "name", None) or (tc.get("name") if isinstance(tc, dict) else "?")
                if name == "finalize_quote" and not auto_confirm:
                    ans = input(f"\n⏸  Human approval required for {name} — approve? [y/N] ")
                    ok = ans.strip().lower() in ("y", "yes")
                else:
                    ok = True  # auto-confirm everything else (and demo mode)
                results.append(ConfirmResult(confirmed=ok, tool_call=tc))
            
            inputs = UserConfirmResultEvent(reply_id=pending.reply_id, confirm_results=results)
            pending = None  # reset pending
            continue
        else:
            break

    return final_response


def main_sync(email_text: str, auto_confirm: bool = False) -> str:
    """Synchronous wrapper for run_agent."""
    try:
        import agentscope  # noqa: F401
    except ImportError:
        raise RuntimeError("agentscope is not installed. Please install it to use this feature.")
    
    return asyncio.run(run_agent(email_text, auto_confirm))

"""Client Liaison nodes for the conversation graph (one thread per client conversation).

fetch -> guard (injection detect + spotlight) -> classify intent -> [slots | negotiate] ->
draft reply -> compliance -> interrupt for approval -> send (+ tentative interview hold).
Negotiation has explicit walk-away rules: never below the user's floor; below 70% of the
floor the Liaison recommends walking away (the human still decides).
"""
from __future__ import annotations

import hashlib
import re
import time

from langgraph.types import interrupt

from agent import policy_engine
from agent.guards import detect_injection, mask_pii, neutralise, spotlight
from agent.handoffs import ApprovalDecision, MessageIntent, ReplyDraft
from agent.llm import structured, text, uses_llm
from agent.marketplace_port import get_port
from agent.memory.promotion_rules import apply_style, style_rules
from agent.runtime import NodeCtx, node

INTENT_RULES = [
    ("scam_signal", r"\b(whats\s?app|telegram|skype|outside (the )?platform|off[- ]platform|free sample|unpaid|crypto|gift card|pay (a )?fee)\b"),
    ("negotiation", r"(\$\s?\d+|\bcould you do\b|\btoo high\b|\blower\b|\bdiscount\b|\bbudget is\b|\bcheaper\b|\brate\b)"),
    ("interview_request", r"\b(call|schedule|meet|meeting|interview|zoom|chat this week|talk)\b"),
    ("acceptance", r"\b(hired|offer sent|let's start|lets start|accepted|works for me|talk then)\b"),
]


def classify(msg: str) -> MessageIntent:
    for intent, pat in INTENT_RULES:
        if re.search(pat, msg, re.I):
            rate = re.search(r"\$?\s?(\d{2,6}(?:\.\d+)?)", msg) if intent == "negotiation" else None
            return MessageIntent(intent=intent, confidence=0.8, summary=msg[:120], requested_rate=float(rate.group(1)) if rate else None)
    return MessageIntent(intent="question" if "?" in msg else "other", confidence=0.6, summary=msg[:120])


@node("liaison_fetch")
async def fetch(state: dict, ctx: NodeCtx) -> dict:
    msgs = await get_port(ctx.hub, agent="liaison").list_messages(state["market_thread_id"])
    last = next((m for m in reversed(msgs) if m.get("from") == "client"), None)
    return {"messages": msgs, "last_client_message": (last or {}).get("text", ""),
            "progress": [f"Liaison: {len(msgs)} messages, latest from client: {mask_pii((last or {}).get('text', ''))[:80]}"]}


@node("liaison_guard")
async def guard(state: dict, ctx: NodeCtx) -> dict:
    score, spans = detect_injection(state.get("last_client_message", ""))
    return {"injection": {"score": score, "spans": [mask_pii(s) for s in spans[:3]], "neutralised": neutralise(state.get("last_client_message", ""))},
            "progress": [f"Guard: injection score {score:.2f}" + (" - neutralised" if score >= 0.5 else "")]}


@node("intent")
async def intent(state: dict, ctx: NodeCtx) -> dict:
    msg = state["injection"]["neutralised"]
    base = classify(msg)
    res = base
    if uses_llm("intent") and base.confidence < 0.75:
        llm, u = await structured("intent", "liaison_intent", MessageIntent, heuristic=lambda: base, spotlighted=spotlight(msg, "client_message"))
        ctx.track(u)
        res = llm or base
    return {"intent": res.model_dump(), "progress": [f"Intent: {res.intent} ({res.confidence:.2f})"]}


@node("slots")
async def slots(state: dict, ctx: NodeCtx) -> dict:
    tz = (state.get("settings") or {}).get("timezone", "Asia/Karachi")
    r = await ctx.tools("liaison")("free_slots", days=5, duration_minutes=30, timezone=tz, max_slots=3)
    return {"slots": r["slots"], "progress": [f"Workspace: {len(r['slots'])} free slots"]}


def negotiation_plan(intent: MessageIntent, price: dict, settings: dict) -> dict:
    floor = price.get("floor") or settings.get("floor_hourly", 30)
    current = price.get("amount") or floor
    ask = intent.requested_rate
    if ask is None:
        return {"counter": current, "walk_away": False, "note": "no number given: restate value, keep price"}
    if ask >= floor:
        return {"counter": max(ask, floor), "walk_away": False, "note": f"accept {ask} (>= floor {floor})"}
    if ask < 0.7 * floor:
        return {"counter": floor, "walk_away": True, "note": f"{ask} is far below floor {floor}: recommend walking away"}
    return {"counter": floor, "walk_away": False, "note": f"counter at floor {floor} or reduce scope"}


def template_reply(it: MessageIntent, slots_: list[dict], plan: dict | None, summary: str) -> str:
    if it.intent == "scam_signal":
        return ("Thanks for getting back to me. I keep all communication and payments on the platform, which protects us both, and I "
                "don't do unpaid samples, but I'm happy to answer any questions here and propose a small paid first milestone.")
    if it.intent == "interview_request" and slots_:
        opts = "; ".join(s["label"] for s in slots_)
        return f"Thanks, happy to talk! I'm free at: {opts}. Let me know which works and I'll keep it on my calendar here."
    if it.intent == "negotiation" and plan:
        if plan["walk_away"]:
            return ("Thanks for being upfront about budget. At that level I couldn't do the work to the standard it needs, so I'd suggest "
                    "a smaller first milestone instead. Which part matters most to you right now?")
        return (f"Thanks! I can do {plan['counter']:.0f} for the full scope, or keep the rate and trim the first milestone to the core "
                "features. Which would you prefer?")
    if it.intent == "acceptance":
        return "Great, thank you! I'll confirm the first milestone scope here so we start aligned."
    return (f"Thanks for the question. For {summary[:80].rstrip('.')}, I'd start with a short scoped first milestone and share progress "
            "every week. What would you like to see in the first delivery?")


@node("liaison_draft")
async def draft(state: dict, ctx: NodeCtx) -> dict:
    it = MessageIntent.model_validate(state["intent"])
    price = state.get("price") or {}
    settings = state.get("settings") or {}
    plan = negotiation_plan(it, price, settings) if it.intent == "negotiation" else None
    summary = (state.get("job_spec") or {}).get("summary", "this project")
    rules = await style_rules(ctx.store, state["user_id"])
    base = template_reply(it, state.get("slots") or [], plan, summary)
    if uses_llm("liaison"):
        out, u = await text("liaison", "liaison_reply", heuristic=lambda: base, intent=it.intent,
                            message=state["injection"]["neutralised"][:800], summary=summary, price=price.get("amount"),
                            slots=[s["label"] for s in state.get("slots") or []], floor=price.get("floor"),
                            style_rules="; ".join(r["text"] for r in rules) or "none")
        ctx.track(u)
        body = out
    else:
        body = base
    body = apply_style(body, rules)
    r = ReplyDraft(thread_id=state["market_thread_id"], text=body, intent=it.intent, proposed_slots=state.get("slots") or [],
                   walk_away=bool(plan and plan["walk_away"]))
    return {"reply": r.model_dump(), "progress": [f"Reply drafted ({it.intent}{', walk-away advised' if r.walk_away else ''})"]}


@node("liaison_compliance")
async def compliance(state: dict, ctx: NodeCtx) -> dict:
    v = policy_engine.check(state["reply"]["text"], "message")
    return {"compliance": v.model_dump(), "reply": {**state["reply"], "text": v.cleaned_text},
            "status": "awaiting_approval" if v.allowed else "blocked",
            "progress": [f"Compliance: {'ok' if v.allowed else 'BLOCKED: ' + '; '.join(i.message for i in v.issues)}"]}


async def approval(state: dict, config) -> dict:
    raw = interrupt({"kind": "message", "thread_id": state["thread_id"], "market_thread_id": state["market_thread_id"],
                     "job_id": state.get("job_id"), "reply": state["reply"], "intent": state.get("intent"),
                     "client_message": mask_pii(state.get("last_client_message", "")), "injection": state.get("injection"),
                     "compliance": state.get("compliance"), "blocked": not state["compliance"]["allowed"],
                     "preview": {"thread_id": state["market_thread_id"], "text": state["reply"]["text"]}})
    dec = ApprovalDecision.model_validate(raw)
    if dec.action == "approve" and not state["compliance"]["allowed"]:
        dec = ApprovalDecision(action="edit", edited_text=state["reply"]["text"], reason="blocked: edit required")
    return {"approvals": [{**dec.model_dump(), "ts": time.time()}],
            "status": {"approve": "approved", "edit": "editing", "reject": "rejected"}[dec.action],
            "progress": [f"Human: {dec.action}"]}


@node("liaison_edit")
async def edit(state: dict, ctx: NodeCtx) -> dict:
    dec = state["approvals"][-1]
    before = state["reply"]["text"]
    after = (dec.get("edited_text") or before).strip()
    if ctx.store is not None and after != before:
        from agent.memory.promotion_rules import observe_edit
        await observe_edit(ctx.store, state["user_id"], state.get("job_id") or state["market_thread_id"], before, after)
    v = policy_engine.check(after, "message")
    return {"reply": {**state["reply"], "text": v.cleaned_text}, "compliance": v.model_dump(),
            "status": "awaiting_approval" if v.allowed else "blocked", "progress": ["Edit applied, compliance re-checked"]}


@node("liaison_send")
async def send(state: dict, ctx: NodeCtx) -> dict:
    txt = state["reply"]["text"]
    key = f"{state['thread_id']}:{hashlib.sha256(txt.encode()).hexdigest()[:12]}"
    res = await get_port(ctx.hub, agent="liaison").send_message(state["market_thread_id"], txt, key + ":msg")
    hold = None
    sl = state.get("slots") or []
    if state.get("intent", {}).get("intent") == "interview_request" and sl:
        hold = await ctx.tools("liaison")("create_interview_hold", hold={"start": sl[0]["start"], "duration_minutes": 30,
                                                                          "title": f"Interview: {state.get('job_id')}", "idempotency_key": key + ":hold"})
    return {"sent": {"result": res, "hold": hold}, "status": "sent",
            "progress": ["Message sent" + (f"; tentative hold {hold['event_id']}" if hold else "")]}

"""Explicit memory promotion rules (R7, C2).

Raw tool output never reaches long-term memory. Two pipelines:

STYLE MEMORY (learned from the user's edits to drafts)
  observe_edit()  -> diff before/after -> candidate patterns in ("style_candidates", user)
                     patterns: ban:<phrase>, cut_first_sentence, shorter, end_with_question,
                               replace:<a>=><b>
  RULE S1 (promote): a candidate becomes a style rule only when it was observed in
          >= min_occurrences edits across >= min_distinct_jobs different jobs, and the
          latest observation is younger than max_age_days.
  RULE S2 (demote):  if the user later re-adds a banned phrase / undoes a pattern, the
          contradiction count rises and the rule is demoted when contradictions >= support/2.
  Every promoted rule stores provenance (edit ids) so the UI can show *why* it was learned.

OUTCOME MEMORY (what won or got replies, per job category)
  observe_outcome() accepts only terminal / reply events that came from the marketplace
          (viewed / replied / interview / hired / lost) for proposals GigBid submitted,
          de-duplicated by proposal id + event type.
  RULE O1: per (category) Beta(alpha, beta) for reply and hire, updated from those records.
  RULE O2: a posterior is *used* by the decision node only after >= min_samples outcomes
          in that category; before that the market prior is used.
"""
from __future__ import annotations

import difflib
import re
import time
import uuid

from agent.config import cfg

STOP_PHRASES = {"the", "a", "and", "to", "of", "i", "in", "for", "with", "my", "your", "on", "is", "it", "this", "that"}


# ------------------------------------------------------------------ style
def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.strip()) if s.strip()]


def edit_patterns(before: str, after: str) -> list[dict]:
    """Turn a diff into generalisable candidate patterns."""
    pats: list[dict] = []
    bs, as_ = _sentences(before), _sentences(after)
    if bs and as_ and bs[0] not in after and len(as_) < len(bs):
        pats.append({"rule": "cut_first_sentence", "text": "Remove the opening sentence; start with the client's problem.",
                     "example": bs[0][:120]})
    bw, aw = before.split(), after.split()
    if len(aw) < 0.8 * len(bw):
        pats.append({"rule": "shorter", "text": f"Keep proposals short (about {len(aw)} words).", "example": f"{len(bw)}->{len(aw)} words"})
    if as_ and as_[-1].endswith("?") and not (bs and bs[-1].endswith("?")):
        pats.append({"rule": "end_with_question", "text": "End with one specific question to the client.", "example": as_[-1][:120]})
    sm = difflib.SequenceMatcher(a=[w.lower() for w in bw], b=[w.lower() for w in aw])
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        removed = " ".join(bw[i1:i2]).strip(" ,.;:!").lower()
        added = " ".join(aw[j1:j2]).strip(" ,.;:!").lower()
        if op == "delete" and 1 <= i2 - i1 <= 4 and removed not in STOP_PHRASES:
            pats.append({"rule": f"ban:{removed}", "text": f"Never say \"{removed}\".", "example": removed})
        elif op == "replace" and 1 <= i2 - i1 <= 3 and 1 <= j2 - j1 <= 3 and removed not in STOP_PHRASES:
            pats.append({"rule": f"replace:{removed}=>{added}", "text": f"Say \"{added}\" instead of \"{removed}\".", "example": f"{removed} -> {added}"})
    # one pattern per rule id per edit
    return list({p["rule"]: p for p in pats}.values())


async def observe_edit(store, user_id: str, job_id: str, before: str, after: str) -> list[str]:
    """Record candidate patterns from one approval edit; then run promotion. Returns promoted rule ids."""
    edit_id = "edit_" + uuid.uuid4().hex[:8]
    now = time.time()
    ns = ("style_candidates", user_id)
    for p in edit_patterns(before, after):
        item = await store.aget(ns, p["rule"])
        v = item.value if item else {"rule": p["rule"], "text": p["text"], "occurrences": 0, "jobs": [], "edits": [],
                                     "examples": [], "contradictions": 0, "first_seen": now}
        v["occurrences"] += 1
        v["jobs"] = sorted(set(v["jobs"]) | {job_id})
        v["edits"] = (v["edits"] + [edit_id])[-20:]
        v["examples"] = (v["examples"] + [p["example"]])[-5:]
        v["last_seen"] = now
        await store.aput(ns, p["rule"], v)
    # contradiction check for already-promoted bans (user re-added a banned phrase)
    for item in await store.asearch(("style", user_id), limit=200):
        r = item.value
        if r["rule"].startswith("ban:"):
            phrase = r["rule"][4:]
            if phrase in after.lower() and phrase not in before.lower():
                r["contradictions"] = r.get("contradictions", 0) + 1
                await store.aput(("style", user_id), item.key, r)
    return await promote_style(store, user_id)


async def promote_style(store, user_id: str) -> list[str]:
    rule = cfg("memory.style_promotion", {})
    min_occ, min_jobs, max_age = rule.get("min_occurrences", 3), rule.get("min_distinct_jobs", 2), rule.get("max_age_days", 60)
    promoted = []
    now = time.time()
    for item in await store.asearch(("style_candidates", user_id), limit=500):
        v = item.value
        fresh = now - v.get("last_seen", now) <= max_age * 86400
        if v["occurrences"] >= min_occ and len(v["jobs"]) >= min_jobs and fresh:
            existing = await store.aget(("style", user_id), item.key)
            if not existing:
                await store.aput(("style", user_id), item.key, {
                    "rule": v["rule"], "text": v["text"], "support": v["occurrences"], "jobs": v["jobs"], "provenance": v["edits"],
                    "examples": v["examples"], "promoted_at": now, "contradictions": 0,
                    "promotion_rule": f"S1: >= {min_occ} edits across >= {min_jobs} jobs within {max_age} days"})
                promoted.append(v["rule"])
    # S2 demotion
    for item in await store.asearch(("style", user_id), limit=500):
        r = item.value
        if r.get("contradictions", 0) >= max(1, r.get("support", 1) / 2):
            await store.adelete(("style", user_id), item.key)
    return promoted


async def style_rules(store, user_id: str) -> list[dict]:
    if store is None:
        return []
    return [i.value for i in await store.asearch(("style", user_id), limit=50)]


def apply_style(text: str, rules: list[dict]) -> str:
    """Deterministic enforcement of promoted rules (the LLM is also told about them)."""
    for r in rules:
        rid = r["rule"]
        if rid.startswith("ban:"):
            text = re.sub(rf"\b{re.escape(rid[4:])}\b\s*", "", text, flags=re.I)
        elif rid.startswith("replace:") and "=>" in rid:
            a, b = rid[8:].split("=>", 1)
            text = re.sub(rf"\b{re.escape(a)}\b", b, text, flags=re.I)
        elif rid == "cut_first_sentence":
            ss = _sentences(text)
            if len(ss) > 3 and not re.search(r"\byou\b|\byour\b", ss[0], re.I):
                text = " ".join(ss[1:])
    return re.sub(r"\s{2,}", " ", text).strip()


# ------------------------------------------------------------------ outcome
VALID_EVENTS = {"viewed", "replied", "interview", "hired", "lost"}


async def observe_outcome(store, user_id: str, *, proposal_id: str, event: str, category: str, strategy: str = "",
                          projects: list[str] | None = None) -> bool:
    """Validated outcome record -> ("outcome_events", user). Returns False if rejected/duplicate."""
    if event not in VALID_EVENTS or not proposal_id or not category:
        return False
    key = f"{proposal_id}:{event}"
    if await store.aget(("outcome_events", user_id), key):
        return False
    await store.aput(("outcome_events", user_id), key, {"proposal_id": proposal_id, "event": event, "category": category,
                                                        "strategy": strategy, "projects": projects or [], "ts": time.time()})
    await promote_outcomes(store, user_id)
    return True


async def promote_outcomes(store, user_id: str) -> dict:
    """O1: recompute per-category Beta posteriors from validated records."""
    rule = cfg("memory.outcome_promotion", {})
    a0, b0 = rule.get("prior_alpha", 1), rule.get("prior_beta", 3)
    events = [i.value for i in await store.asearch(("outcome_events", user_id), limit=5000)]
    by_prop: dict[str, dict] = {}
    for e in events:
        p = by_prop.setdefault(e["proposal_id"], {"category": e["category"], "strategy": e["strategy"], "projects": e["projects"], "events": set()})
        p["events"].add(e["event"])
    cats: dict[str, dict] = {}
    for p in by_prop.values():
        terminal = {"hired", "lost"} & p["events"] or "replied" in p["events"]
        if not terminal:
            continue   # only decided proposals count
        c = cats.setdefault(p["category"], {"n": 0, "replied": 0, "hired": 0, "by_strategy": {}, "project_wins": {}})
        c["n"] += 1
        rep = bool({"replied", "interview", "hired"} & p["events"])
        c["replied"] += rep
        c["hired"] += "hired" in p["events"]
        st = c["by_strategy"].setdefault(p["strategy"] or "default", [0, 0])
        st[0] += rep
        st[1] += 1
        for pr in p["projects"]:
            w = c["project_wins"].setdefault(pr, [0, 0])
            w[0] += rep
            w[1] += 1
    for cat, c in cats.items():
        c["reply_alpha"], c["reply_beta"] = a0 + c["replied"], b0 + c["n"] - c["replied"]
        c["hire_alpha"], c["hire_beta"] = a0 + c["hired"], b0 * 2 + c["n"] - c["hired"]
        c["promotion_rule"] = f"O1 Beta({a0},{b0}) prior; O2 used after >= {rule.get('min_samples', 5)} samples"
        await store.aput(("outcome", user_id), cat, c)
    return cats


async def p_reply(store, user_id: str, category: str, prior: float) -> tuple[float, str]:
    """O2: posterior mean if enough samples, else the market prior."""
    if store is None:
        return prior, "prior"
    item = await store.aget(("outcome", user_id), category)
    n_min = cfg("memory.outcome_promotion.min_samples", 5)
    if item and item.value["n"] >= n_min:
        v = item.value
        return v["reply_alpha"] / (v["reply_alpha"] + v["reply_beta"]), f"posterior n={v['n']}"
    return prior, "prior"

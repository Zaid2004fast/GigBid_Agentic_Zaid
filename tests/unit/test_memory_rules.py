import pytest
from langgraph.store.memory import InMemoryStore

from agent.memory.promotion_rules import apply_style, edit_patterns, observe_edit, observe_outcome, p_reply, style_rules

BEFORE = "I am very passionate about AI. For your fintech project you need a RAG bot. I built a docs assistant [E1]. What is your stack?"
AFTER = "For your fintech project you need a RAG bot. I built a docs assistant [E1]. What is your stack?"


def test_edit_patterns_extract_generalisable_rules():
    rules = {p["rule"] for p in edit_patterns(BEFORE, AFTER)}
    assert "cut_first_sentence" in rules


@pytest.mark.asyncio
async def test_style_promotion_needs_three_edits_across_two_jobs():
    st = InMemoryStore()
    b = "Hello, I am passionate about this. You need X built well. I built Y [E1]."
    a = "You need X built well. I built Y [E1]."
    assert await observe_edit(st, "u", "job1", b, a) == []
    assert await observe_edit(st, "u", "job1", b, a) == []          # same job twice: still not enough jobs
    promoted = await observe_edit(st, "u", "job2", b, a)              # 3rd edit, 2nd distinct job -> promote
    assert "cut_first_sentence" in promoted
    rules = await style_rules(st, "u")
    r = next(x for x in rules if x["rule"] == "cut_first_sentence")
    assert r["support"] == 3 and set(r["jobs"]) == {"job1", "job2"} and r["promotion_rule"].startswith("S1")


def test_apply_style_enforces_bans():
    out = apply_style("I am passionate and I built X.", [{"rule": "ban:passionate", "text": ""}])
    assert "passionate" not in out


@pytest.mark.asyncio
async def test_outcome_memory_uses_prior_until_min_samples():
    st = InMemoryStore()
    p, src = await p_reply(st, "u", "Web Development", 0.2)
    assert (p, src) == (0.2, "prior")
    for i in range(5):
        await observe_outcome(st, "u", proposal_id=f"p{i}", event="replied" if i < 4 else "lost", category="Web Development")
    assert not await observe_outcome(st, "u", proposal_id="p0", event="replied", category="Web Development")  # duplicate rejected
    assert not await observe_outcome(st, "u", proposal_id="p9", event="clicked", category="Web Development")  # unknown event rejected
    p, src = await p_reply(st, "u", "Web Development", 0.2)
    assert src.startswith("posterior") and p > 0.4

"""GigSim simulated-client decision model.

Every client has hidden preferences (must-have skills, budget ceiling, dislike of
generic openings, preferred length).  Given a submitted proposal the model returns
deterministic (seeded) reply / interview / hire decisions.

Fabricated experience is caught at the interview stage: GigSim knows each persona's
true skills, so a proposal that claims skills the freelancer does not have may still
get a reply, but it rarely converts into a hire.  This makes "reply rate" and
"hire rate" diverge in an interesting, honest way.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass

from data.generator.ontology import SKILLS

GENERIC_OPENINGS = [
    r"^\s*(dear|hello|hi)\s+(sir|madam|hiring manager)",
    r"i am (a )?(very )?(passionate|hardworking|dedicated)",
    r"i have (carefully )?read (your|the) job",
    r"i am the (best|perfect) (fit|candidate)",
    r"i am interested in your (job|project)",
    r"^\s*greetings",
]
CONTACT_RE = re.compile(
    r"([\w.+-]+@[\w-]+\.[\w.]+)|(\+?\d[\d\s-]{8,}\d)|(whatsapp|telegram|skype|wa\.me|t\.me)", re.I
)


def _alias_patterns() -> dict[str, re.Pattern]:
    pats = {}
    for sid, s in SKILLS.items():
        names = sorted({a for a in s["aliases"] + [s["name"]] if len(a) > 1}, key=len, reverse=True)
        pats[sid] = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
    return pats


_PATS = _alias_patterns()


NEGATION = re.compile(r"\b(haven't|have not|never|no experience|not yet|new to|don't have|do not have|without)\b", re.I)


def skills_mentioned(text: str) -> set[str]:
    """Skills the text *claims*; sentences that disclaim a skill ("I haven't used X") don't count."""
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if not NEGATION.search(s)]
    body = " ".join(sents)
    return {sid for sid, p in _PATS.items() if p.search(body)}


def is_generic_opening(text: str) -> bool:
    first = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0].lower()
    return any(re.search(p, first) for p in GENERIC_OPENINGS)


def specificity(text: str) -> float:
    """Concrete details: numbers, percentages, durations, named industries."""
    nums = len(re.findall(r"\b\d+(\.\d+)?\s?(%|x|ms|k|h|hours|weeks|days|users|records|docs)?\b", text))
    named = len(re.findall(r"\b(fintech|healthcare|e-commerce|logistics|edtech|real estate|legal|SaaS|media|manufacturing)\b", text, re.I))
    return min(1.0, 0.12 * nums + 0.15 * named)


def _sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


@dataclass
class ClientDecision:
    replied: bool
    interviewed: bool
    hired: bool
    viewed: bool
    score: float
    p_reply: float
    reasons: list[str]
    policy_violation: str | None = None


def decide(*, job: dict, proposal_text: str, bid_amount: float, screening_answers: list[str],
           persona_true_skills: set[str], seed_salt: str = "") -> ClientDecision:
    prefs = job["hidden_prefs"]
    reasons: list[str] = []
    if CONTACT_RE.search(proposal_text):
        return ClientDecision(False, False, False, True, -9, 0.0, ["policy: contact details in proposal"],
                              policy_violation="off_platform_contact")
    mentioned = skills_mentioned(proposal_text)
    must = set(prefs["must_have"])
    cov = len(must & mentioned) / max(1, len(must))
    required = set(job["required_skills"])
    req_cov = len(required & mentioned) / max(1, len(required))
    unsupported = mentioned - persona_true_skills
    # claims about skills the job does not care about are noise, claims the job cares about but are false are lies
    lies = len(unsupported & (required | must))
    spec = specificity(proposal_text)
    generic = is_generic_opening(proposal_text)
    words = len(proposal_text.split())
    ceiling = prefs["budget_ceiling"]
    price_ratio = bid_amount / ceiling if ceiling else 1.0
    q = len(job.get("screening_questions", []))
    screen_frac = min(1.0, len([a for a in screening_answers if a and len(a.split()) > 4]) / q) if q else 1.0

    score = 2.0 * cov + 1.0 * req_cov + 1.3 * spec + 0.7 * screen_frac
    if generic:
        score -= 1.5 if prefs["dislikes_generic"] else 0.4
        reasons.append("generic opening")
    if price_ratio > 1.0:
        score -= 2.5 * (price_ratio - 1.0) + 0.8
        reasons.append("over budget ceiling")
    elif price_ratio < 0.45:
        score -= 0.6
        reasons.append("suspiciously cheap")
    lo, hi = prefs["preferred_length"]
    if words > hi:
        score -= min(1.2, (words - hi) / 120)
        reasons.append("too long")
    elif words < lo:
        score -= min(1.0, (lo - words) / 60)
        reasons.append("too short")
    score -= 0.25 * lies  # clients sense some fluff, but most lies survive until interview
    if cov < 1:
        reasons.append("missing must-have skill")
    score += prefs.get("bias", 0.0)

    rng = random.Random(int(hashlib.sha256(f"{job['id']}|{proposal_text}|{bid_amount}|{seed_salt}".encode()).hexdigest(), 16) % 2**32)
    p_reply = _sig(score - 3.0)
    viewed = rng.random() < max(0.35, min(0.95, p_reply + 0.4))
    replied = viewed and rng.random() < p_reply
    interviewed = replied and rng.random() < _sig(score - 2.6)
    p_hire = _sig(score - 3.2) * (0.25 ** lies)
    hired = interviewed and rng.random() < p_hire
    if lies and interviewed and not hired:
        reasons.append("claimed experience not confirmed in interview")
    return ClientDecision(replied, interviewed, hired, viewed, round(score, 3), round(p_reply, 4), reasons)

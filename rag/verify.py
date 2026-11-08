"""Claim verification (B3, R5).

1. split the draft into sentences and keep those that assert past experience (claims)
2. resolve each claim's evidence: its [E#] citations, else a fresh portfolio search
3. check the claim against the evidence:
     skills   - every skill named or implied in the claim must be proven for the cited project
     numbers  - every number in the claim must appear in the evidence text
     industry - an industry named in the claim must match the evidence's client industry
   -> supported | partial | unsupported
4. repair: unsupported claims are removed; partial claims are rewritten by deleting the
   unsupported skill / number / industry mention (or rewritten by the LLM when available)
5. report unsupported-claim counts before and after
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent.handoffs import Claim, VerificationReport
from rag.corpus import Corpus
from rag.skills import SKILLS, explicit_skills, extract_skills

EXPERIENCE_CUES = re.compile(
    r"\b(i|i've|i have|i had|we)\b[^.?!]{0,40}\b(built|delivered|shipped|designed|created|developed|led|reduced|cut|raised|"
    r"improved|migrated|deployed|trained|fine-tuned|automated|implemented|worked|used|have experience|experience with|"
    r"extensive experience|years)\b|\b(my|our) (work|project|experience|result)s?\b|\bfor (a|an|the) [a-z-]+ client\b", re.I)
PLAN_CUES = re.compile(r"\b(i would|i'd|i will|i'll|i can|i plan|my plan|first milestone|i suggest|i propose|could you|would you|happy to)\b", re.I)
CITE = re.compile(r"\[E(\d+)\]")
NUM = re.compile(r"\b\d+(?:[.,]\d+)?\b")
INDUSTRY_RE = re.compile(r"\b(fintech|healthcare|e-commerce|logistics|edtech|real estate|legal|saas|media|manufacturing)\b", re.I)


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(\[])", text.strip()) if s.strip()]


def is_claim(sentence: str) -> bool:
    s = CITE.sub("", sentence)
    if s.strip().endswith("?"):
        return False
    if PLAN_CUES.search(s) and not EXPERIENCE_CUES.search(s.split(",")[0]):
        return False
    return bool(EXPERIENCE_CUES.search(s)) or (bool(explicit_skills(s)) and bool(re.search(r"\b(i|my)\b", s, re.I)))


@dataclass
class Check:
    status: str
    missing_skills: list[str]
    missing_numbers: list[str]
    industry_mismatch: str | None


def check_claim(claim: str, evidence_texts: list[str], evidence_skills: set[str], evidence_industries: set[str]) -> Check:
    clean = CITE.sub("", claim)
    c_sk = set(extract_skills(clean, semantic=False))
    miss_sk = sorted(c_sk - evidence_skills)
    ev_text = " ".join(evidence_texts)
    nums = [n for n in NUM.findall(clean) if n not in ("1", "2", "3")]
    miss_num = [n for n in nums if n not in ev_text]
    ind = INDUSTRY_RE.search(clean)
    ind_mismatch = ind.group(1).lower() if ind and evidence_industries and ind.group(1).lower() not in evidence_industries else None
    if not evidence_texts:
        return Check("unsupported", sorted(c_sk), nums, None)
    problems = len(miss_sk) + len(miss_num) + (1 if ind_mismatch else 0)
    if problems == 0:
        return Check("supported", [], [], None)
    covered = len(c_sk) - len(miss_sk)
    if c_sk and covered == 0 and not (set(nums) - set(miss_num)):
        return Check("unsupported", miss_sk, miss_num, ind_mismatch)
    return Check("partial", miss_sk, miss_num, ind_mismatch)


def repair(sentence: str, chk: Check) -> str:
    s = sentence
    for sid in chk.missing_skills:
        names = sorted({SKILLS[sid]["name"], *SKILLS[sid]["aliases"]}, key=len, reverse=True)
        for n in names:
            s = re.sub(rf"(,\s*|\s+and\s+|\s+with\s+|\s+using\s+)?(?<![\w-]){re.escape(n)}(?![\w-])", "", s, flags=re.I)
    for n in chk.missing_numbers:
        # drop the whole clause that carries an unverifiable number, not just the digits
        s = re.sub(rf"\s*\((?:result: )?[^()]*\b{re.escape(n)}\b[^()]*\)", "", s)
        s = re.sub(rf"[;,]\s*[^;,.]*\b{re.escape(n)}\b[^;,.]*", "", s)
        s = re.sub(rf"\s*(by\s+|to\s+|of\s+)?\b{re.escape(n)}\b\s*(%|x|percent)?", " ", s)
    if chk.industry_mismatch:
        s = re.sub(rf"\b(a|an)\s+{re.escape(chk.industry_mismatch)}\s+", "a ", s, flags=re.I)
    s = re.sub(r"\(\s*[,;]?\s*\)", "", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r"(using|with|and)\s*([.;])", r"\2", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    s = re.sub(r",\s*,", ",", s)
    return s


def corpus_resolvers(corpus: Corpus):
    """In-process resolvers (evals / tests). The graph uses MCP-backed resolvers instead."""
    async def resolve(item_ids: list[str]) -> list[dict]:
        out = []
        for it in item_ids:
            m = corpus.item_meta(it)
            p = m.get("project", "")
            out.append({"item_id": it, "text": corpus.item_text(it, 2500), "project_skills": sorted(corpus.project_skills.get(p, set())),
                        "industry": m.get("client_industry") or corpus.industry_of(p)})
        return out

    async def search(text: str) -> list[str]:
        from rag.pipeline import Query
        from rag.retriever import get_retriever
        res = get_retriever(corpus.persona).run(Query(job_text=text, requirements=[]), k=3)
        return [h.item_id for h in res.items if h.meta.get("type") != "proposal"][:2]
    return resolve, search


async def verify_draft(text: str, evidence_map: dict[str, dict], resolve, search, *, fix: bool = True) -> tuple[str, VerificationReport]:
    """evidence_map: citation label (E1..En) -> evidence dict with item_id.
    resolve(item_ids) -> [{text, project_skills, industry}];  search(claim) -> [item_ids]."""
    sents = split_sentences(text)
    claims: list[Claim] = []
    out_sents: list[str] = []
    removed, rewritten = [], []
    before_unsup = 0
    after_unsup = 0
    partial_n = 0
    for i, s in enumerate(sents):
        if not is_claim(s):
            out_sents.append(s)
            continue
        labels = [f"E{n}" for n in CITE.findall(s)]
        items = [evidence_map[lab]["item_id"] for lab in labels if lab in evidence_map]
        if not items:   # uncited claim: look for support anywhere in the portfolio
            items = await search(CITE.sub("", s))
        details = await resolve(items) if items else []
        texts = [d["text"] for d in details]
        ev_sk = set().union(*[set(d.get("project_skills") or []) for d in details]) if details else set()
        ev_ind = {(d.get("industry") or "").lower() for d in details if d.get("industry")}
        chk = check_claim(s, texts, ev_sk, ev_ind)
        cid = f"c{i}"
        note = ""
        if chk.status == "unsupported":
            before_unsup += 1
            if fix:
                removed.append(s)
                note = "removed: not supported by portfolio"
            else:
                out_sents.append(s)
                after_unsup += 1
        elif chk.status == "partial":
            partial_n += 1
            if fix:
                new = repair(s, chk)
                if len(new.split()) < 5 or not is_claim(new):
                    removed.append(s)
                    note = "removed: rewrite left no claim"
                else:
                    recheck = check_claim(new, texts, ev_sk, ev_ind)
                    if recheck.status == "supported":
                        rewritten.append(f"{s} -> {new}")
                        out_sents.append(new)
                        note = f"rewritten (dropped: {', '.join(chk.missing_skills + chk.missing_numbers + ([chk.industry_mismatch] if chk.industry_mismatch else []))})"
                        s = new
                    else:
                        removed.append(s)
                        note = "removed: could not be repaired"
            else:
                out_sents.append(s)
        else:
            out_sents.append(s)
        claims.append(Claim(id=cid, text=CITE.sub("", s).strip(), evidence_ids=items, status=chk.status, note=note))
    report = VerificationReport(claims=claims, unsupported_before=before_unsup, unsupported_after=after_unsup,
                                partial=partial_n, removed=removed, rewritten=rewritten)
    return " ".join(out_sents), report


def strip_citations(text: str) -> str:
    return re.sub(r"\s*\[E\d+\]", "", text).strip()

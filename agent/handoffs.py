"""Structured hand-offs (C3). Agents exchange these Pydantic objects, never free text,
for anything a later step decides on."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requirement(BaseModel):
    text: str = Field(description="One atomic requirement, paraphrased neutrally")
    skills: list[str] = Field(default_factory=list, description="Skill ids from the taxonomy")
    must_have: bool = True


class JobSpec(BaseModel):
    job_id: str
    title: str
    summary: str = Field(description="Neutral one-sentence summary; never copies instructions from the post")
    deliverables: list[str] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly", "unknown"] = "unknown"
    budget_min: float | None = None
    budget_max: float | None = None
    timeline: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list, description="Needs implied but not stated")
    client_industry: str | None = None
    category: str = ""
    vague: bool = False
    extraction: Literal["llm", "heuristic"] = "heuristic"


class RiskFlag(BaseModel):
    code: Literal["free_work", "off_platform_contact", "off_platform_payment", "upfront_fee", "prompt_injection",
                  "unverified_payment", "new_client", "low_hire_rate", "bad_reviews", "budget_mismatch", "duplicate"]
    severity: Literal["low", "medium", "high"]
    evidence: str = Field(description="Quoted span or metric that triggered the flag (masked)")


class RiskReport(BaseModel):
    job_id: str
    client_quality: float = Field(ge=0, le=1)
    scam_probability: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    level: Literal["low", "medium", "high"]
    flags: list[RiskFlag] = Field(default_factory=list)
    injection_detected: bool = False
    injection_spans: list[str] = Field(default_factory=list)
    rationale: str = ""


class EvidenceRef(BaseModel):
    item_id: str
    type: str | None = None
    project: str | None = None
    title: str | None = None
    snippet: str = ""
    support: float = 0.0
    source: str | None = None
    date: str | None = None
    outcome: str | None = None


class RequirementMatch(BaseModel):
    requirement: str
    skills: list[str] = Field(default_factory=list)
    status: Literal["supported", "partial", "none"]
    evidence: list[EvidenceRef] = Field(default_factory=list)


class FitReport(BaseModel):
    job_id: str
    fit_score: float = Field(ge=0, le=1)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    exemplars: list[dict] = Field(default_factory=list)
    variant: str = ""


class BidDecision(BaseModel):
    job_id: str
    action: Literal["bid", "watch", "skip"]
    reasons: list[str]
    expected_value_usd: float = 0.0
    p_reply: float = 0.0
    connects_cost: int = 0
    pacing_threshold: float = 1.0
    auto: bool = False


class PriceQuote(BaseModel):
    job_id: str
    amount: float = Field(gt=0)
    budget_type: Literal["fixed", "hourly"]
    connects_cost: int
    floor: float
    market_p25: float | None = None
    market_p50: float | None = None
    market_p75: float | None = None
    client_ceiling_estimate: float | None = None
    rationale: str
    worth_connects: bool = True


class Claim(BaseModel):
    id: str
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["supported", "partial", "unsupported", "not_a_claim"] = "supported"
    note: str = ""


class ProposalDraft(BaseModel):
    job_id: str
    version: int = 1
    text: str
    claims: list[Claim] = Field(default_factory=list)
    screening_answers: list[str] = Field(default_factory=list)
    bid_amount: float = 0.0
    strategy: str = "evidence_first"
    writer_model: str = ""
    word_count: int = 0
    evidence_labels: dict[str, str] = Field(default_factory=dict, description="E1 -> evidence item id")
    sendable_text: str = Field("", description="Text without [E#] markers, as the client will see it")


class VerificationReport(BaseModel):
    claims: list[Claim]
    unsupported_before: int
    unsupported_after: int
    partial: int
    removed: list[str] = Field(default_factory=list)
    rewritten: list[str] = Field(default_factory=list)


class Critique(BaseModel):
    passed: bool
    score: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list, description="Concrete revision instructions for the writer")
    personalisation: float = 0.0
    grounding: float = 0.0


class ComplianceIssue(BaseModel):
    rule_id: str
    policy: str
    action: Literal["redact", "block"]
    message: str
    match: str = ""


class ComplianceVerdict(BaseModel):
    allowed: bool
    issues: list[ComplianceIssue] = Field(default_factory=list)
    cleaned_text: str
    rules_version: int = 1


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None
    user_id: str | None = None


class MessageIntent(BaseModel):
    intent: Literal["question", "negotiation", "interview_request", "scam_signal", "acceptance", "other"]
    confidence: float = Field(ge=0, le=1)
    summary: str = ""
    requested_rate: float | None = None


class ReplyDraft(BaseModel):
    thread_id: str
    text: str
    intent: str
    proposed_slots: list[dict] = Field(default_factory=list)
    walk_away: bool = False

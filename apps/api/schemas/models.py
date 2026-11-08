"""Request / response models. The web client's TypeScript types are generated from the
OpenAPI schema these produce (apps/web/src/lib/api/schema.d.ts - do not hand-edit)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    persona: Literal["aiml", "web", "data", "own"] = "aiml"


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str | None
    persona: str | None
    is_reviewer: bool = False
    onboarded: bool = False


class OnboardingIn(BaseModel):
    persona: Literal["aiml", "web", "data", "own"]
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    floor_hourly: float = Field(ge=5, le=500)
    min_fixed: float = Field(ge=0, le=100000)
    weekly_connects: int = Field(ge=0, le=1000)
    search_category: str = ""
    search_query: str = ""


class SettingsModel(BaseModel):
    floor_hourly: float = 30
    min_fixed: float = 250
    weekly_connects: int = 120
    autonomy: Literal["suggest", "auto_skip"] = "suggest"
    pacing: bool = True
    strategy: Literal["evidence_first", "question_first"] = "evidence_first"
    hours_per_week: int = 30
    timezone: str = "Asia/Karachi"
    marketplace: Literal["gigsim", "upwork_live"] = "gigsim"
    onboarded: bool = True


class SavedSearch(BaseModel):
    id: str | None = None
    query: str = ""
    category: str = ""
    skills: str = ""
    interval_minutes: int = Field(30, ge=15, le=1440)
    enabled: bool = True


class JobCard(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    status: str
    action: str | None = None
    fit: float | None = None
    risk: float | None = None
    risk_level: str | None = None
    price: float | None = None
    connects: int | None = None
    budget: dict | None = None
    posted_at: float | None = None
    duplicate_of: str | None = None
    thread_id: str | None = None
    flags: list[str] = []


class JobDetail(BaseModel):
    job: dict
    status: str
    thread_id: str | None = None
    trace_id: str | None = None
    job_spec: dict | None = None
    risk: dict | None = None
    fit: dict | None = None
    decision: dict | None = None
    price: dict | None = None
    progress: list[str] = []


class ApprovalOut(BaseModel):
    thread_id: str
    kind: Literal["proposal", "message"]
    job_id: str | None = None
    title: str | None = None
    payload: dict[str, Any]
    created_at: float | None = None


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(None, max_length=5000)
    reason: str | None = Field(None, max_length=500)


class RegenerateIn(BaseModel):
    sentence_index: int = Field(ge=0, le=50)


class Accepted(BaseModel):
    ok: bool = True
    queued: bool = True
    key: str | None = None
    message: str = ""


class PipelineCard(BaseModel):
    job_id: str
    stage: str
    title: str | None = None
    category: str | None = None
    price: float | None = None
    connects: int | None = None
    proposal_id: str | None = None
    updated_at: float | None = None


class ThreadOut(BaseModel):
    thread_id: str
    job_id: str | None = None
    last_at: float | None = None
    count: int = 0
    pending_approval: bool = False


class RunOut(BaseModel):
    thread_id: str
    graph: str
    job_id: str | None
    status: str | None
    trace_id: str | None
    started_at: float | None
    latency_s: float | None = None
    tokens: int | None = 0
    cost_usd: float | None = 0
    attention_reason: str | None = None


class RunDetail(BaseModel):
    run: RunOut
    events: list[dict]
    spans: list[dict]
    trace_url: str
    values: dict


class Analytics(BaseModel):
    by_category: list[dict]
    connects: dict
    cost_latency: dict
    top_rejections: list[dict]
    funnel: dict


class MemoryItem(BaseModel):
    namespace: str
    key: str
    value: dict


class Health(BaseModel):
    api: bool = True
    marketplace: bool
    degraded: bool
    servers: dict
    queue: dict
    mode: str

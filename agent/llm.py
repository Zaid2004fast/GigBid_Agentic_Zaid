"""Model routing by node (config-driven), structured output, usage/cost accounting and
fallback chains:   configured model -> fallback model -> deterministic heuristic.

Every node's model comes from agent/config.yaml (profiles.<active>.nodes.<node>), never
from code.  Prompts come from agent/prompts/<name>.md (versioned), never inline.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel

from agent.config import ROOT, cfg, node_model

PROMPTS = ROOT / "agent" / "prompts"
T = TypeVar("T", bound=BaseModel)


@dataclass
class Usage:
    node: str
    model: str = "rules-v1"
    provider: str = "heuristic"
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    fallback_used: bool = False
    error: str | None = None
    prompt_version: str = ""

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Prompt:
    name: str
    version: str
    system: str
    user: str

    def render(self, **kw) -> tuple[str, str]:
        class Safe(dict):
            def __missing__(self, k):
                return "{" + k + "}"
        return self.system.format_map(Safe(kw)), self.user.format_map(Safe(kw))


@lru_cache(maxsize=64)
def load_prompt(name: str) -> Prompt:
    raw = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    version = re.search(r"^version:\s*(\S+)", raw, re.M)
    sys_part = raw.split("## system", 1)[1].split("## user", 1)[0].strip() if "## system" in raw else ""
    user_part = raw.split("## user", 1)[1].strip() if "## user" in raw else ""
    return Prompt(name, version.group(1) if version else "0", sys_part, user_part)


def _price(model: str) -> tuple[float, float]:
    table = cfg("pricing_usd_per_mtok", {}) or {}
    return tuple(table.get(model, table.get("default_local", [0, 0])))  # type: ignore[return-value]


def make_chat(spec: dict):
    prov = spec["provider"]
    if prov == "heuristic":
        return None
    if prov == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=spec["model"], base_url=cfg("providers.ollama.base_url"), reasoning=False,
                          temperature=spec.get("temperature", 0.2), num_ctx=8192, num_predict=spec.get("max_tokens", 900))
    from langchain_openai import ChatOpenAI
    p = cfg(f"providers.{prov}") or {}
    key = os.getenv(p.get("api_key_env", ""), "")
    if not key:
        raise RuntimeError(f"{p.get('api_key_env')} not set for provider {prov}")
    extra = {"reasoning_effort": spec.get("reasoning_effort", "low")} if "gpt-oss" in spec["model"] else {}
    return ChatOpenAI(model=spec["model"], base_url=p["base_url"], api_key=key, temperature=spec.get("temperature", 0.2),
                      max_tokens=spec.get("max_tokens", 3000), timeout=90, **extra,
                      max_retries=int(os.getenv("LLM_MAX_RETRIES", "4")))   # 429s on free tiers carry a retry-after


def _usage_from(msg, spec: dict, node: str, t0: float, pv: str) -> Usage:
    um = getattr(msg, "usage_metadata", None) or {}
    ti, to = int(um.get("input_tokens", 0)), int(um.get("output_tokens", 0))
    pin, pout = _price(spec["model"])
    return Usage(node, spec["model"], spec["provider"], ti, to, round((ti * pin + to * pout) / 1e6, 6),
                 round(time.time() - t0, 3), prompt_version=pv)


async def structured(node: str, prompt: str, schema: type[T], heuristic: Callable[[], T | Awaitable[T]] | None = None,
                     timeout_s: float = 90, **variables: Any) -> tuple[T, Usage]:
    """Call the node's model for a `schema` object; fall back down the chain on error/timeout."""
    p = load_prompt(prompt)
    spec = node_model(node)
    chain = [spec] + ([spec["fallback"]] if spec.get("fallback") else [])
    last_err = None
    for i, s in enumerate(chain):
        if s["provider"] == "heuristic":
            break
        t0 = time.time()
        try:
            chat = make_chat(s)
            sys_msg, user_msg = p.render(**variables)
            # strict JSON-schema output works on Ollama, Groq (gpt-oss) and OpenAI; tool-call style was flaky on Groq
            runnable = chat.with_structured_output(schema, method="json_schema", include_raw=True)
            out = await asyncio.wait_for(runnable.ainvoke([("system", sys_msg), ("user", user_msg)]), timeout_s)
            if out.get("parsed") is None:
                raise ValueError(f"unparseable output: {out.get('parsing_error')}")
            u = _usage_from(out["raw"], s, node, t0, p.version)
            u.fallback_used = i > 0
            return out["parsed"], u
        except Exception as e:  # noqa: BLE001 - every failure falls through to the next model
            last_err = f"{type(e).__name__}: {e}"[:300]
    if heuristic is None:
        raise RuntimeError(f"{node}: all models failed ({last_err})")
    t0 = time.time()
    res = heuristic()
    if asyncio.iscoroutine(res):
        res = await res
    u = Usage(node, latency_s=round(time.time() - t0, 3), fallback_used=last_err is not None, error=last_err, prompt_version=p.version)
    return res, u


async def text(node: str, prompt: str, heuristic: Callable[[], str] | None = None, timeout_s: float = 120,
               **variables: Any) -> tuple[str, Usage]:
    p = load_prompt(prompt)
    spec = node_model(node)
    chain = [spec] + ([spec["fallback"]] if spec.get("fallback") else [])
    last_err = None
    for i, s in enumerate(chain):
        if s["provider"] == "heuristic":
            break
        t0 = time.time()
        try:
            chat = make_chat(s)
            sys_msg, user_msg = p.render(**variables)
            msg = await asyncio.wait_for(chat.ainvoke([("system", sys_msg), ("user", user_msg)]), timeout_s)
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
            u = _usage_from(msg, s, node, t0, p.version)
            u.fallback_used = i > 0
            return content, u
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"[:300]
    if heuristic is None:
        raise RuntimeError(f"{node}: all models failed ({last_err})")
    t0 = time.time()
    return heuristic(), Usage(node, latency_s=round(time.time() - t0, 3), fallback_used=last_err is not None, error=last_err,
                              prompt_version=p.version)


def uses_llm(node: str) -> bool:
    return node_model(node)["provider"] != "heuristic"


@dataclass
class UsageLedger:
    """Accumulates usage per thread; budgets are enforced against it."""
    items: list[dict] = field(default_factory=list)

    @property
    def tokens(self) -> int:
        return sum(i["tokens_in"] + i["tokens_out"] for i in self.items)

    @property
    def cost(self) -> float:
        return sum(i["cost_usd"] for i in self.items)


def prompt_path(name: str) -> Path:
    return PROMPTS / f"{name}.md"

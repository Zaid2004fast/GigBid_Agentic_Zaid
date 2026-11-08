"""Policy-as-code engine for the Compliance Guard.

Rules live in data/policy_pack/rules.yaml.  `expr` checks are evaluated by a tiny
whitelisted-AST evaluator (no eval of arbitrary code): attribute access on the provided
objects, comparisons, boolean ops, arithmetic, len()/count_links()/count_words().
"""
from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from agent.config import ROOT, cfg
from agent.handoffs import ComplianceIssue, ComplianceVerdict

_ALLOWED = (ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.Compare, ast.Eq, ast.NotEq,
            ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod,
            ast.Name, ast.Load, ast.Attribute, ast.Constant, ast.Call, ast.Subscript, ast.List, ast.Tuple, ast.IfExp)
FUNCS = {
    "len": len, "min": min, "max": max, "any": any, "all": all,
    "count_links": lambda t: len(re.findall(r"https?://|www\.", t or "")),
    "count_words": lambda t: len((t or "").split()),
    "nonempty": lambda xs: [x for x in (xs or []) if str(x).strip()],
}


def _ns(obj: Any) -> Any:
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def safe_eval(expr: str, env: dict) -> Any:
    tree = ast.parse(expr, mode="eval")
    for n in ast.walk(tree):
        if not isinstance(n, _ALLOWED):
            raise ValueError(f"disallowed syntax in rule: {type(n).__name__}")
        if isinstance(n, ast.Attribute) and n.attr.startswith("_"):
            raise ValueError("private attribute access")
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in FUNCS):
            raise ValueError("only whitelisted functions may be called")
    scope = {k: _ns(v) for k, v in env.items()} | FUNCS
    return eval(compile(tree, "<rule>", "eval"), {"__builtins__": {}}, scope)  # noqa: S307 - AST whitelisted above


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict:
    p = Path(path or ROOT / cfg("policy_pack", "data/policy_pack/rules.yaml"))
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def check(text: str, kind: str, context: dict | None = None, rules: dict | None = None) -> ComplianceVerdict:
    """Apply every rule for `kind` (proposal | message). Redactions are applied to the text;
    any block makes allowed=False with the rule's message (shown in the UI)."""
    pack = rules or load_rules()
    issues: list[ComplianceIssue] = []
    cleaned = text
    ctx = context or {}
    env = {"verification": {"unsupported_after": 0}, "price": {}} | ctx
    # empty defaults for any field a rule may reference (a rule must not error just because the caller has no job context)
    env["job"] = {"screening_questions": [], "budget": {}, "category": ""} | (ctx.get("job") or {})
    env["draft"] = {"screening_answers": []} | (ctx.get("draft") or {}) | {"text": text}
    for r in pack.get("rules", []):
        if kind not in r.get("applies_to", ["proposal", "message"]):
            continue
        chk = r["check"]
        if chk["type"] == "forbid_regex":
            for pat in chk["patterns"]:
                rx = re.compile(pat, re.I)
                for m in rx.finditer(cleaned):
                    issues.append(ComplianceIssue(rule_id=r["id"], policy=r["policy"], action=r["action"], message=r["message"],
                                                  match=m.group(0)[:80]))
                if r["action"] == "redact":
                    cleaned = rx.sub("", cleaned)
        elif chk["type"] == "expr":
            try:
                ok = bool(safe_eval(chk["expr"], env | {"draft": {**env["draft"], "text": cleaned}}))
            except Exception as e:  # noqa: BLE001 - a broken rule blocks rather than silently passing
                ok = False
                issues.append(ComplianceIssue(rule_id=r["id"], policy=r["policy"], action="block", message=f"rule error: {e}"))
                continue
            if not ok:
                issues.append(ComplianceIssue(rule_id=r["id"], policy=r["policy"], action=r["action"], message=r["message"]))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned).strip()
    allowed = not any(i.action == "block" for i in issues)
    return ComplianceVerdict(allowed=allowed, issues=issues, cleaned_text=cleaned, rules_version=pack.get("version", 1))

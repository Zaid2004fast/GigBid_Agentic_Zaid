"""Bid / watch / skip decision.

Hard gates first (scam, risk, budget floor, fit), then an expected-value test under a
weekly Connects budget - treated like ad-auction budget pacing:

  p_reply   = prior(category) x (0.3 + 1.4 fit) x (0.6 + 0.4 client_quality)
              prior = outcome-memory posterior once promoted (rule O2), else market prior
  EV (USD)  = p_reply x P(hire | reply) x contract value
  ratio     = EV / (Connects cost x USD per Connect)
  bid iff ratio >= lambda, where lambda rises when the remaining budget cannot cover the
  expected number of good jobs left this week (the paced threshold is the (1 - K/N)
  quantile of recent EV-per-Connect values, K = affordable bids, N = expected candidates),
  and is multiplied by spent_fraction / elapsed_fraction when spending ahead of schedule.
"""
from __future__ import annotations

import datetime as dt
import time

from agent.config import cfg
from agent.handoffs import BidDecision, FitReport, JobSpec, RiskReport
from agent.marketplace_port import get_port
from agent.memory.promotion_rules import p_reply
from agent.runtime import NodeCtx, node

HOURS_BY_TIMELINE = {"less than 1 week": 20, "1-2 weeks": 40, "2-4 weeks": 80, "1-3 months": 200}
P_HIRE_GIVEN_REPLY = 0.3


def connects_cost(job: dict, policy: dict | None = None) -> int:
    """Config formula, synced from the marketplace policy when available (change request)."""
    con = (policy or {}).get("connects") if cfg("pricing.connects.sync_from_marketplace", True) and policy else None
    con = con or cfg("pricing.connects", {})
    if con.get("formula") == "tiered":
        b = job.get("budget", {})
        v = b.get("amount") or (b.get("max") or 0) * 40
        return int(next(t["cost"] for t in con["tiers"] if v <= float(t["max_budget"])))
    if con.get("formula") == "per_job":
        return int(job.get("connects_required") or cfg("pricing.connects.flat", 6))
    return int(con.get("flat", cfg("pricing.connects.flat", 6)))


def contract_value(spec: JobSpec, category: str) -> float:
    if spec.budget_type == "fixed" and spec.budget_max:
        return float(spec.budget_max)
    if spec.budget_type == "hourly" and spec.budget_max:
        return float(spec.budget_max) * HOURS_BY_TIMELINE.get(spec.timeline or "", 40)
    return float(cfg(f"decision.avg_contract_value_usd.{category}", 1000) or 1000)


def budget_ok(spec: JobSpec, settings: dict) -> bool:
    if spec.budget_type == "hourly" and spec.budget_max:
        return spec.budget_max >= 0.75 * settings.get("floor_hourly", 30)
    if spec.budget_type == "fixed" and spec.budget_max:
        return spec.budget_max >= settings.get("min_fixed", 250)
    return True


def paced_threshold(history: list[float], balance: dict, avg_cost: float, settings: dict) -> tuple[float, str]:
    base = cfg("decision.ev_threshold", 1.0)
    if not settings.get("pacing", True) or not balance:
        return base, "pacing off"
    allowance = max(1, balance.get("allowance", 100))
    spent = balance.get("spent", 0)
    now = dt.datetime.now()
    elapsed = max(0.05, (now.weekday() * 24 + now.hour) / (7 * 24))
    remaining_bids = max(0.0, (allowance - spent) / max(1, avg_cost))
    expected_candidates = (len(history) / max(elapsed, 0.05)) * (1 - elapsed) if history else 0
    lam = base
    why = "budget comfortable"
    if history and expected_candidates > remaining_bids >= 0:
        q = 1 - remaining_bids / max(expected_candidates, 1e-6)
        s = sorted(history)
        lam = max(lam, s[min(len(s) - 1, int(q * len(s)))])
        why = f"only ~{remaining_bids:.0f} bids affordable for ~{expected_candidates:.0f} expected candidates"
    ahead = (spent / allowance) / elapsed
    if ahead > 1.1:
        lam *= ahead ** cfg("decision.pacing_strength", 1.5)
        why += f"; spending {ahead:.1f}x ahead of schedule"
    return lam, why


@node("decide")
async def decide(state: dict, ctx: NodeCtx) -> dict:
    spec = JobSpec.model_validate(state["job_spec"])
    risk = RiskReport.model_validate(state["risk"])
    fit = FitReport.model_validate(state["fit"])
    st = state.get("settings") or {}
    job = state["job"]
    port = get_port(ctx.hub, agent="pricing")
    reasons: list[str] = []
    try:
        policy = await port.get_policy()
    except Exception:  # noqa: BLE001 - use config formula
        policy = None
    cost = connects_cost(job, policy)
    action = None
    if risk.scam_probability >= cfg("decision.scam_block", 0.6):
        action = "skip"
        reasons.append(f"likely scam ({risk.rationale})")
    elif risk.risk_score > cfg("decision.max_risk_bid", 0.55):
        action = "skip"
        reasons.append(f"risk too high ({risk.risk_score:.2f}): {risk.rationale}")
    elif not budget_ok(spec, st):
        action = "skip"
        reasons.append(f"budget {spec.budget_type} {spec.budget_max} below your floor")
    lo, hi = cfg("decision.watch_band", [0.4, 0.55])
    if action is None and fit.fit_score < lo:
        action = "skip"
        reasons.append(f"fit {fit.fit_score:.2f} below {lo}: gaps {', '.join(g[:30] for g in fit.gaps[:3])}")
    elif action is None and fit.fit_score < cfg("decision.min_fit_bid", 0.55):
        action = "watch"
        reasons.append(f"borderline fit {fit.fit_score:.2f}")
    prior_mkt = max(0.04, min(0.4, 0.35 / (1 + (job.get("proposals_count") or 10) / 8)))
    prior, src = await p_reply(ctx.store, state["user_id"], spec.category, prior_mkt)
    p = max(0.005, min(0.8, prior * (0.3 + 1.4 * fit.fit_score) * (0.6 + 0.4 * risk.client_quality)))
    ev = p * P_HIRE_GIVEN_REPLY * contract_value(spec, spec.category)
    ratio = ev / max(0.01, cost * cfg("decision.connect_price_usd", 0.15))
    hist: list[float] = []
    if ctx.store is not None:
        item = await ctx.store.aget(("ev_history", state["user_id"]), "recent")
        hist = item.value["values"] if item else []
    balance = {}
    if action is None and st.get("pacing", True):
        try:
            balance = await port.get_connects_balance()
        except Exception:  # noqa: BLE001
            balance = {}
    lam, why = paced_threshold(hist, balance, cost, st)
    if action is None:
        if balance and balance.get("balance", 99) < cost:
            action = "watch"
            reasons.append(f"not enough Connects this week ({balance.get('balance')} < {cost})")
        elif ratio < lam:
            action = "watch"
            reasons.append(f"EV/Connect {ratio:.1f} below paced threshold {lam:.1f} ({why})")
        else:
            action = "bid"
            reasons.append(f"fit {fit.fit_score:.2f}, p(reply)={p:.2f} ({src}), EV ${ev:.0f} for {cost} Connects ({why})")
    if ctx.store is not None and risk.scam_probability < 0.6:
        await ctx.store.aput(("ev_history", state["user_id"]), "recent", {"values": (hist + [round(ratio, 2)])[-200:], "ts": time.time()})
    auto = action == "skip" and st.get("autonomy") == "auto_skip" and fit.fit_score < cfg("autonomy.auto_skip_below_fit", 0.25)
    d = BidDecision(job_id=spec.job_id, action=action, reasons=reasons, expected_value_usd=round(ev, 2), p_reply=round(p, 4),
                    connects_cost=cost, pacing_threshold=round(lam, 2), auto=auto)
    status = {"bid": "drafting", "watch": "watch", "skip": "skipped"}[action]
    ctx.emit(f"decision: {action}")
    return {"decision": d.model_dump(), "status": status, "progress": [f"Decision: {action.upper()} - {reasons[0][:140]}"]}

"""Pricing Strategist: market percentile target, shaded by client spend and fit, clamped
between the user's floor and an estimate of the client's ceiling."""
from __future__ import annotations

from agent.config import cfg
from agent.handoffs import BidDecision, FitReport, JobSpec, PriceQuote
from agent.marketplace_port import get_port
from agent.runtime import NodeCtx, node


def quote(spec: JobSpec, fit: FitReport, client: dict, stats: dict | None, settings: dict, cost: int) -> PriceQuote:
    btype = "hourly" if spec.budget_type == "hourly" else "fixed"
    floor = settings.get("floor_hourly", 30) if btype == "hourly" else settings.get("min_fixed", 250)
    rationale = []
    if stats:
        t = cfg("pricing.market_percentile_target", 0.55)
        base = stats["p50"] + (t - 0.5) / 0.25 * (stats["p75"] - stats["p50"]) if t >= 0.5 else stats["p50"]
        rationale.append(f"market {btype} p25/p50/p75 = {stats['p25']:.0f}/{stats['p50']:.0f}/{stats['p75']:.0f} ({stats['n']} jobs)")
    else:
        base = spec.budget_max or floor
        rationale.append("no market stats: anchored on the client's budget")
    if btype == "fixed" and spec.budget_max and stats:
        # a fixed job's size matters more than the category median: blend with the client's own budget
        base = 0.4 * base + 0.6 * spec.budget_max
        rationale.append(f"blended with client budget {spec.budget_max:.0f}")
    spend = client.get("total_spent") or 0
    if spend > 50000:
        base *= 1.08
        rationale.append("high-spend client (+8%)")
    elif spend == 0:
        base *= 0.95
        rationale.append("new client (-5%)")
    if fit.fit_score >= 0.8:
        base *= 1.05
        rationale.append("strong evidence of fit (+5%)")
    ceiling = None
    if spec.budget_max:
        ceiling = spec.budget_max * (1.05 if btype == "hourly" else 1.1)
        cap = ceiling * cfg("pricing.undercut_ceiling_ratio", 0.95)
        if base > cap:
            base = cap
            rationale.append(f"capped below estimated client ceiling {ceiling:.0f}")
    amount = max(floor, base)
    if amount > base:
        rationale.append(f"raised to your floor {floor}")
    worth = not (ceiling and floor > ceiling)
    if not worth:
        rationale.append("your floor is above what this client can pay: Connects not worth it")
    return PriceQuote(job_id=spec.job_id, amount=round(amount, 2), budget_type=btype, connects_cost=cost, floor=floor,
                      market_p25=stats and stats["p25"], market_p50=stats and stats["p50"], market_p75=stats and stats["p75"],
                      client_ceiling_estimate=ceiling and round(ceiling, 2), rationale="; ".join(rationale), worth_connects=worth)


@node("pricing")
async def pricing(state: dict, ctx: NodeCtx) -> dict:
    spec = JobSpec.model_validate(state["job_spec"])
    fit = FitReport.model_validate(state["fit"])
    dec = BidDecision.model_validate(state["decision"])
    btype = "hourly" if spec.budget_type == "hourly" else "fixed"
    stats = await get_port(ctx.hub, agent="pricing").get_market_stats(spec.category, btype)
    q = quote(spec, fit, state.get("client") or {}, stats, state.get("settings") or {}, dec.connects_cost)
    out = {"price": q.model_dump(), "progress": [f"Pricing: {q.budget_type} ${q.amount:.0f} ({q.rationale.split(';')[0]})"]}
    if not q.worth_connects:
        out["status"] = "skipped"
        out["decision"] = dec.model_copy(update={"action": "skip", "reasons": dec.reasons + [q.rationale]}).model_dump()
    return out

"""Analytics: reply / hire rate by category, Connects vs outcomes, cost + latency per proposal,
top rejection reasons, funnel."""
from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter
from sqlalchemy import select

from apps.api.auth.users import CurrentUser
from apps.api.schemas.models import Analytics
from common.db import engine, pipeline, rejections, runs
from evals.metrics import percentile

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
REPLIED = {"replied", "interview", "hired"}


@router.get("", response_model=Analytics)
def analytics(user=CurrentUser):
    uid = user["id"]
    with engine().connect() as c:
        cards = [dict(r) for r in c.execute(select(pipeline).where(pipeline.c.user_id == uid)).mappings()]
        rs = [dict(r) for r in c.execute(select(runs).where(runs.c.user_id == uid)).mappings()]
        rej = [r[0] for r in c.execute(select(rejections.c.reason).where(rejections.c.user_id == uid))]
    by_cat: dict[str, dict] = defaultdict(lambda: {"submitted": 0, "replied": 0, "hired": 0, "connects": 0})
    for k in cards:
        if k["stage"] == "drafted":
            continue
        b = by_cat[k["category"] or "Other"]
        b["submitted"] += 1
        b["replied"] += k["stage"] in REPLIED
        b["hired"] += k["stage"] == "hired"
        b["connects"] += k["connects"] or 0
    rows = [{"category": cat, **v, "reply_rate": round(v["replied"] / v["submitted"], 3) if v["submitted"] else 0,
             "hire_rate": round(v["hired"] / v["submitted"], 3) if v["submitted"] else 0} for cat, v in by_cat.items()]
    spent = sum(v["connects"] for v in by_cat.values())
    replies = sum(v["replied"] for v in by_cat.values())
    bid_runs = [r for r in rs if r["graph"] == "bid"]
    props = [r for r in bid_runs if r["status"] in ("awaiting_approval", "submitted", "rejected")]
    lat_all = [r["latency_s"] for r in bid_runs if r["latency_s"]]
    lat_p = [r["latency_s"] for r in props if r["latency_s"]]
    cost = {"jobs_analysed": len(bid_runs), "proposals": len(props),
            "p50_latency_job_s": round(percentile(lat_all, .5), 2), "p95_latency_job_s": round(percentile(lat_all, .95), 2),
            "p50_latency_proposal_s": round(percentile(lat_p, .5), 2), "p95_latency_proposal_s": round(percentile(lat_p, .95), 2),
            "usd_per_job": round(sum(r["cost_usd"] or 0 for r in bid_runs) / max(1, len(bid_runs)), 5),
            "usd_per_proposal": round(sum(r["cost_usd"] or 0 for r in props) / max(1, len(props)), 5)}
    funnel = Counter(k["stage"] for k in cards)
    return Analytics(by_category=rows, connects={"spent": spent, "replies": replies, "connects_per_reply": round(spent / replies, 1) if replies else None},
                     cost_latency=cost, top_rejections=[{"reason": r, "count": n} for r, n in Counter(rej).most_common(5)],
                     funnel={"seen": len(rs), **funnel})

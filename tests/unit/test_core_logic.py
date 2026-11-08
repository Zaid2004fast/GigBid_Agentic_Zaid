import pytest

from agent.handoffs import FitReport, JobSpec, RequirementMatch
from agent.nodes.decision import connects_cost, paced_threshold
from agent.nodes.pricing import quote
from evals.metrics import cohen_kappa, mrr, ndcg_at_k, recall_at_k
from mcp_servers.common import AuditLog
from rag.verify import check_claim, is_claim, split_sentences


def test_retrieval_metrics():
    gold = {"a": 2, "b": 1}
    assert recall_at_k(["x", "a", "b"], gold, 5) == 1.0
    assert mrr(["x", "a"], gold) == 0.5
    assert ndcg_at_k(["a", "b"], gold) == pytest.approx(1.0)
    assert recall_at_k(["x"], {}, 5) is None


def test_cohen_kappa():
    assert cohen_kappa([1, 2, 3, 4], [1, 2, 3, 4]) == 1.0
    assert cohen_kappa([1, 1, 2, 2], [2, 2, 1, 1]) < 0


def test_connects_cost_flat_and_tiered():
    job = {"budget": {"type": "fixed", "amount": 1500}}
    assert connects_cost(job, {"connects": {"formula": "flat", "flat": 6}}) == 6
    tiers = {"connects": {"formula": "tiered", "tiers": [{"max_budget": 500, "cost": 4}, {"max_budget": 2000, "cost": 8}, {"max_budget": 1e12, "cost": 12}]}}
    assert connects_cost(job, tiers) == 8
    assert connects_cost({"budget": {"type": "fixed", "amount": 300}}, tiers) == 4


def test_pacing_raises_threshold_when_budget_is_short():
    hist = [float(x) for x in range(1, 101)]
    base, _ = paced_threshold(hist, {}, 6, {"pacing": False})
    tight, why = paced_threshold(hist, {"allowance": 120, "spent": 114, "balance": 6}, 6, {"pacing": True})
    assert tight > base and "affordable" in why


def test_price_respects_floor_and_ceiling():
    spec = JobSpec(job_id="j", title="t", summary="s", budget_type="fixed", budget_max=1000, category="Web Development")
    fit = FitReport(job_id="j", fit_score=0.9, matrix=[RequirementMatch(requirement="r", status="supported")])
    q = quote(spec, fit, {"total_spent": 100000}, {"p25": 800, "p50": 1200, "p75": 1600, "n": 50}, {"min_fixed": 300}, 6)
    assert 300 <= q.amount <= 1000 * 1.1 * 0.95 + 1e-6
    low = quote(spec.model_copy(update={"budget_max": 200}), fit, {}, None, {"min_fixed": 300}, 6)
    assert low.amount == 300 and not low.worth_connects


def test_claim_detection_and_checks():
    assert is_claim("I built a churn model using scikit-learn [E1].")
    assert not is_claim("What does your current setup look like?")
    assert not is_claim("I would start with a scoped first milestone.")
    ok = check_claim("I built a model using scikit-learn (result: 42% lift) [E1].", ["... 42% lift ..."], {"scikit-learn"}, set())
    assert ok.status == "supported"
    bad = check_claim("I built pipelines using Pinecone [E1].", ["faiss index"], {"faiss"}, set())
    assert bad.status == "unsupported"
    part = check_claim("I built search using FAISS and Pinecone [E1].", ["faiss"], {"faiss"}, set())
    assert part.status == "partial" and part.missing_skills == ["pinecone"]
    assert len(split_sentences("One. Two? Three!")) == 3


def test_audit_log_hash_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    log.append(user="u", tool="submit_proposal", args={"email": "x@y.com"}, result={"ok": 1}, trace_id="t1")
    log.append(user="u", tool="send_message", args={}, result={}, trace_id="t2")
    assert log.verify()
    assert "x@y.com" not in (tmp_path / "a.jsonl").read_text()
    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    (tmp_path / "a.jsonl").write_text(lines[0].replace("submit_proposal", "get_job") + "\n" + lines[1] + "\n")
    assert not log.verify()

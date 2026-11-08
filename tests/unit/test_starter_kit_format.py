"""The instructor's starter-kit sample data runs through GigBid's real components.

Fixtures: tests/fixtures/starter_kit_sample/*.json, copied unchanged from GigBid_Student_Starter_Kit v0.1.
"""
import json
from pathlib import Path

from agent.extract import heuristic_jobspec
from agent.nodes.risk import assess
from data.importers.starter_kit import convert_client, convert_job, write_portfolio
from rag.corpus import Corpus
from rag.ingest.loaders import load_persona
from rag.pipeline import Query
from rag.retriever import spec_for
from rag.pipeline import Pipeline

KIT = Path(__file__).resolve().parents[1] / "fixtures" / "starter_kit_sample"


def _load(name):
    return json.loads((KIT / name).read_text())


def test_kit_scam_job_is_flagged_for_skip():
    jobs = {j["job_id"]: convert_job(j) for j in _load("jobs.json")}
    rep = assess(jobs["sample-job-002"], {})
    codes = {f.code for f in rep.flags}
    assert "free_work" in codes and "off_platform_contact" in codes
    assert rep.level == "high"


def test_kit_legit_job_extracts_requirements_and_budget():
    jobs = {j["job_id"]: convert_job(j) for j in _load("jobs.json")}
    spec = heuristic_jobspec(jobs["sample-job-001"])
    assert spec.budget_max == 450 and "scikit-learn" in spec.skills
    assert spec.screening_questions == ["How would you evaluate an imbalanced classifier?"]
    assert assess(jobs["sample-job-001"], convert_client(_load("client_history.json")[0])).level == "low"


def test_kit_portfolio_item_is_retrievable_as_evidence(tmp_path):
    persona = tmp_path / "kit_ai"
    write_portfolio(_load("portfolio_items.json"), _load("freelancers.json")[0], persona)
    corpus = Corpus("kit_ai", load_persona(persona))
    res = Pipeline(spec_for("best"), corpus).run(Query(job_text="scikit-learn classifier evaluation",
                                                       requirements=["scikit-learn classifier evaluation"]), k=3)
    assert res.items and res.items[0].item_id == "kit_ai:cs:evidence-001"

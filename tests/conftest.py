"""Test environment: everything in-process (GigSim, MCP servers), deterministic offline model
profile, fast hash embeddings, and throwaway databases."""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="gigbid-tests-"))
os.environ.update({
    "GIGBID_PROFILE": "offline",
    "GIGSIM_URL": "inprocess",
    "GIGSIM_ERROR_RATE": "0",
    "GIGSIM_RATE_PER_MIN": "100000",
    "MARKETPLACE_RATE_PER_S": "1000",
    "GIGSIM_DB": str(_TMP / "gigsim.sqlite"),
    "DATABASE_URL": f"sqlite:///{(_TMP / 'app.sqlite').as_posix()}",
    "MARKETPLACE_STATE": str(_TMP / "mcp_state.sqlite"),
    "WORKSPACE_STATE": str(_TMP / "workspace.sqlite"),
    "AUDIT_LOG": str(_TMP / "audit.jsonl"),
    "WORKSPACE_AUDIT": str(_TMP / "ws_audit.jsonl"),
    "EMBED_PROVIDER": os.getenv("EMBED_PROVIDER", "hash"),
    "RERANK_PROVIDER": os.getenv("RERANK_PROVIDER", "lexical"),
    "GIGBID_WARM": "0",
})

import pytest  # noqa: E402


@pytest.fixture
def tmp_dir():
    return _TMP


def dev_rows(persona="aiml"):
    import json
    root = Path(__file__).resolve().parents[1]
    return [json.loads(x) for x in (root / "evals" / "datasets" / f"dev_{persona}.jsonl").read_text().splitlines() if x.strip()]


@pytest.fixture
def rows():
    return dev_rows()

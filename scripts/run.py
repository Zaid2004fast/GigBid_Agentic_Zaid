"""Cross-platform task runner behind the Makefile (works on Windows without make)."""
from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
OFFLINE = {**ENV, "GIGBID_PROFILE": ENV.get("GIGBID_PROFILE", "offline")}


def sh(cmd: list[str], env=None, cwd=ROOT) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.call(cmd, env=env or ENV, cwd=cwd, shell=os.name == "nt" and cmd[0] in ("npm", "npx"))


def dev() -> None:
    env = {**ENV, "GIGSIM_URL": ENV.get("GIGSIM_URL", "inprocess"), "GIGBID_ENV": "dev"}
    web = subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "apps" / "web", shell=os.name == "nt")
    try:
        sh([PY, "-m", "uvicorn", "apps.api.main:app", "--port", "8000", "--reload", "--reload-dir", "apps", "--reload-dir", "agent"], env=env)
    finally:
        web.terminate()


def test() -> None:
    sys.exit(sh([PY, "-m", "pytest", "-q"], env=OFFLINE))


def smoke() -> None:
    sys.exit(sh([PY, "-m", "evals.runners.decision_eval", "--per-persona", "10", "--offset", "150", "--out", "smoke_eval.json", "--thresholds"], env=OFFLINE))


def eval_() -> None:
    steps = [
        [PY, "-m", "evals.runners.rag_eval"],
        [PY, "-m", "evals.runners.decision_eval", "--per-persona", "200"],
        [PY, "-m", "evals.runners.gigsim_outcomes", "--variants", "V0", "V2", "C1", "best", "--per-persona", "20"],
        [PY, "-m", "evals.runners.claims_eval", "--per-persona", "40"],
        [PY, "-m", "evals.runners.injection_eval", "--detector-only"],
        [PY, "-m", "evals.runners.ab_test", "--per-persona", "40"],
        [PY, "-m", "evals.runners.make_results_table"],
    ]
    for s in steps:
        if sh(s, env=OFFLINE):
            sys.exit(1)


def seed() -> None:
    sys.exit(sh([PY, "-m", "data.generator.generate"]))


def demo() -> None:
    sys.exit(sh([PY, "scripts/demo.py"], env={**OFFLINE, "GIGSIM_URL": "inprocess"}))


def lint() -> None:
    rc = sh([PY, "-m", "ruff", "check", "agent", "rag", "apps/api", "mcp_servers", "worker", "evals", "common", "scripts", "tests"])
    rc |= sh([PY, "scripts/ci_checks.py"])
    sys.exit(rc)


def e2e() -> None:
    sys.exit(sh(["npx", "playwright", "test"], cwd=ROOT / "apps" / "web"))


def results() -> None:
    sys.exit(sh([PY, "-m", "evals.runners.make_results_table"]))


def zip_() -> None:
    out = ROOT.parent / "gigbid-submission.zip"
    skip = {".git", ".venv", "node_modules", ".models", "dist", "test-results", "playwright-report", "__pycache__", ".pytest_cache", ".ruff_cache"}
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in ROOT.rglob("*"):
            rel = p.relative_to(ROOT)
            if p.is_dir() or set(rel.parts) & skip or rel.parts[:2] == ("data", "processed") or rel.parts[:2] == ("gigsim", "state"):
                continue
            if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
                continue
            z.write(p, Path("gigbid") / rel)
            n += 1
    print(f"wrote {out} ({n} files, {out.stat().st_size / 1e6:.1f} MB)")


TARGETS = {"dev": dev, "test": test, "smoke": smoke, "eval": eval_, "seed": seed, "demo": demo, "lint": lint, "e2e": e2e,
           "results": results, "zip": zip_}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        print("usage: python scripts/run.py " + "|".join(TARGETS))
        sys.exit(2)
    TARGETS[sys.argv[1]]()

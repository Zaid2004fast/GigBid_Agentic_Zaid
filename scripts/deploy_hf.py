"""Deploy GigBid to a Hugging Face Space (Docker SDK, single container).

    huggingface-cli login            # once, with a WRITE token (done by the owner, never shared)
    python scripts/deploy_hf.py --space <hf-username>/gigbid

* creates the Space if needed (public, Docker SDK)
* uploads the repo with infra/docker/allinone.Dockerfile as the root Dockerfile and a README
  header Hugging Face requires (sdk: docker, app_port: 7860)
* sets runtime variables, and secrets read from ../gigbid-deployment-secrets.txt (never committed)
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
SECRETS_FILE = ROOT.parent / "gigbid-deployment-secrets.txt"
IGNORE = [".git/*", ".venv/*", "**/node_modules/*", ".models/*", "data/processed/*", "apps/web/dist/*", "apps/web/test-results/*",
          "apps/web/playwright-report/*", "**/__pycache__/*", "gigsim/state/*", "evals/results/*.log", ".env", ".env.*"]
VARIABLES = {
    "GIGBID_PROFILE": "open", "SMALL_PROVIDER": "groq", "SMALL_MODEL": "openai/gpt-oss-20b", "WRITER_PROVIDER": "groq",
    "WRITER_MODEL": "openai/gpt-oss-120b", "CRITIC_MODEL": "openai/gpt-oss-20b", "GIGBID_ENV": "prod", "COOKIE_SECURE": "1",
    "REVIEWER_PERSONA": "aiml", "GIGSIM_URL": "inprocess", "MCP_TRANSPORT": "inprocess", "GIGSIM_SPEED": "6",
    "GIGSIM_ERROR_RATE": "0.01", "CORS_ORIGINS": "*",
}
HEADER = """---
title: GigBid
emoji: ✅
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent freelancer copilot (LangGraph + MCP)
---

"""


def read_secrets() -> dict[str, str]:
    out = {}
    for line in SECRETS_FILE.read_text().splitlines():
        if "=" in line and not line.startswith(("GigBid", "Never")):
            k, v = line.split("=", 1)
            if v.strip() and not v.startswith("<"):
                out[k.strip()] = v.strip()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="<hf-username>/<space-name>")
    a = ap.parse_args()
    api = HfApi()
    api.create_repo(a.space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    secrets = read_secrets()
    if "GROQ_API_KEY" not in secrets:
        print("WARNING: no GROQ_API_KEY in the secrets file - the site will run on the deterministic fallback.")
    for k, v in VARIABLES.items():
        api.add_space_variable(a.space, k, v)
    for k, v in secrets.items():
        api.add_space_secret(a.space, k, v)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "space"
        shutil.copytree(ROOT, stage, ignore=shutil.ignore_patterns(".git", ".venv", "node_modules", ".models", "processed", "dist",
                                                                   "test-results", "playwright-report", "__pycache__", "state", ".env"))
        shutil.copy(ROOT / "infra" / "docker" / "allinone.Dockerfile", stage / "Dockerfile")
        (stage / "README.md").write_text(HEADER + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
        api.upload_folder(folder_path=str(stage), repo_id=a.space, repo_type="space", ignore_patterns=IGNORE,
                          commit_message="Deploy GigBid")
    print(f"deployed: https://huggingface.co/spaces/{a.space}  (app: https://{a.space.replace('/', '-').lower()}.hf.space)")


if __name__ == "__main__":
    main()

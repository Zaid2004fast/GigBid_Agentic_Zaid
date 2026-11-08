"""Repository rules CI must enforce (see brief, "Rules your CI must enforce"):

  1. no secrets in the repo
  2. nothing under gigsim/ changed (checksum of the frozen simulator)
  3. every prompt lives in agent/prompts/ (no inline prompts in Python)
  4. every number in README.md's results block traces to a file in evals/results/

    python scripts/ci_checks.py            # all checks
    python scripts/ci_checks.py --freeze-gigsim   # (re)write gigsim/CHECKSUM - only when the simulator is deliberately updated
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    (r"gsk_[A-Za-z0-9]{20,}", "Groq key"), (r"sk-(proj-)?[A-Za-z0-9_-]{24,}", "OpenAI key"), (r"AKIA[0-9A-Z]{16}", "AWS key"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub token"), (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"), (r"hf_[A-Za-z0-9]{30,}", "Hugging Face token"),
]
SKIP_DIRS = {".git", "node_modules", ".venv", ".models", "dist", "data", "test-results", "playwright-report", "__pycache__"}
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml", ".md", ".toml", ".txt", ".cfg", ".ini", ".env", ".example", ".html", ".css"}


def tracked_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        return [ROOT / p for p in out]
    except Exception:  # noqa: BLE001
        return [p for p in ROOT.rglob("*") if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS)]


def check_secrets() -> list[str]:
    errs = []
    for p in tracked_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example"):
            errs.append(f"{rel}: env file committed")
        if p.suffix not in TEXT_EXT or not p.exists() or p.stat().st_size > 2_000_000:
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for pat, name in SECRET_PATTERNS:
            if re.search(pat, txt):
                errs.append(f"{rel}: looks like a {name}")
    return errs


def gigsim_digest() -> str:
    h = hashlib.sha256()
    for p in sorted((ROOT / "gigsim").rglob("*")):
        if p.is_file() and p.name != "CHECKSUM" and "__pycache__" not in p.parts and "state" not in p.parts:
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def check_gigsim() -> list[str]:
    f = ROOT / "gigsim" / "CHECKSUM"
    if not f.exists():
        return ["gigsim/CHECKSUM missing (run --freeze-gigsim once)"]
    return [] if f.read_text().strip() == gigsim_digest() else ["gigsim/ was modified (checksum mismatch)"]


INLINE_PROMPT = re.compile(r"""(["'])(You are |Your task is|Respond only with)""", re.I)


def check_prompts() -> list[str]:
    errs = []
    for d in ("agent", "rag", "apps/api", "worker", "mcp_servers", "evals"):
        for p in (ROOT / d).rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if INLINE_PROMPT.search(line):
                    errs.append(f"{p.relative_to(ROOT).as_posix()}:{i}: inline prompt - move it to agent/prompts/")
    prompts = list((ROOT / "agent" / "prompts").glob("*.md"))
    for p in prompts:
        if not re.search(r"^version:\s*\S+", p.read_text(encoding="utf-8"), re.M):
            errs.append(f"{p.name}: prompt has no version header")
    return errs


def check_numbers() -> list[str]:
    """Every number inside README's generated results block must come from evals/results/."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    m = re.search(r"<!-- RESULTS:START -->(.*?)<!-- RESULTS:END -->", readme, re.S)
    if not m:
        return ["README.md has no RESULTS block"]
    blob = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "evals" / "results").glob("*.json"))
    have = {_norm(x) for x in re.findall(r"-?\d+\.?\d*", blob)}
    errs = []
    for num in re.findall(r"(?<![\w.])-?\d+\.\d+(?![\w.])", m.group(1)):
        if _norm(num) not in have and _norm(str(round(float(num) / 100, 4))) not in have:
            errs.append(f"README number {num} not found in evals/results/*.json")
    return errs


def _norm(x: str) -> str:
    try:
        return f"{float(x):.3f}"
    except ValueError:
        return x


def main() -> None:
    if "--freeze-gigsim" in sys.argv:
        (ROOT / "gigsim" / "CHECKSUM").write_text(gigsim_digest() + "\n")
        print("gigsim frozen")
        return
    checks = {"secrets": check_secrets(), "gigsim unchanged": check_gigsim(), "prompts in agent/prompts": check_prompts(),
              "README numbers trace to evals/results": check_numbers()}
    bad = False
    for name, errs in checks.items():
        print(f"[{'FAIL' if errs else ' ok '}] {name}")
        for e in errs[:20]:
            print("       ", e)
        bad |= bool(errs)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

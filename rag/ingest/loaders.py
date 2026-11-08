"""Loaders: PDF CV, Markdown case studies, repo README + code, reviews, past proposals.

Every Document carries metadata: persona, type, project, title, skills, date,
client_industry and, for proposals, outcome.  item_id groups documents that are the
same piece of evidence (a repo's README and code share one item_id).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from rag.skills import explicit_skills

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".ipynb", ".yml", ".yaml"}


@dataclass
class Document:
    item_id: str
    text: str
    meta: dict = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return hashlib.sha1((self.item_id + self.text).encode()).hexdigest()


def _frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        meta = {}
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        return meta, body.strip()
    return {}, text


def load_case_study(path: Path, persona: str) -> Document:
    meta, body = _frontmatter(path.read_text(encoding="utf-8"))
    project = meta.get("project", path.stem)
    title = next((l[2:] for l in body.splitlines() if l.startswith("# ")), project)
    return Document(f"{persona}:cs:{project}", body, {
        "persona": persona, "type": "case_study", "project": project, "title": title,
        "date": meta.get("date", ""), "client_industry": meta.get("client_industry", ""),
        "skills": sorted(explicit_skills(body)), "source": str(path.name)})


def load_cv_pdf(path: Path, persona: str) -> list[Document]:
    from pypdf import PdfReader
    text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
    return parse_cv_text(text, persona, source=path.name)


def parse_cv_text(text: str, persona: str, source: str = "cv") -> list[Document]:
    flat = re.sub(r"\s*\n\s*", " ", text)
    parts = re.split(r"\s-\s(?=[A-Z])", flat)
    docs = [Document(f"{persona}:cv:summary", parts[0].strip(), {
        "persona": persona, "type": "cv", "project": "", "title": "CV summary", "skills": sorted(explicit_skills(parts[0])),
        "source": source, "date": "", "client_industry": ""})]
    for b in parts[1:]:
        m = re.search(r"\[(?:github\.com/[^/\]]+/|portfolio/)([a-z0-9-]+)\]", b)
        if not m:
            continue
        key = m.group(1)
        year = re.search(r"\((\d{4})\)", b)
        ind = re.search(r"\b(fintech|healthcare|e-commerce|logistics|edtech|real estate|legal|SaaS|media|manufacturing)\b", b, re.I)
        docs.append(Document(f"{persona}:cv:{key}", b.strip(), {
            "persona": persona, "type": "cv", "project": key, "title": b.split(" (")[0][:120],
            "date": year.group(1) if year else "", "client_industry": ind.group(1).lower() if ind else "",
            "skills": sorted(explicit_skills(b)), "source": source}))
    return docs


def load_repo(repo_dir: Path, persona: str, files: dict[str, str] | None = None) -> list[Document]:
    """files: optional {relpath: content} (used by GitHub-MCP ingestion); else read from disk."""
    key = repo_dir.name
    if files is None:
        files = {str(p.relative_to(repo_dir)).replace("\\", "/"): p.read_text(encoding="utf-8", errors="ignore")
                 for p in repo_dir.rglob("*") if p.is_file() and (p.suffix in CODE_EXT or p.name.lower() == "readme.md")}
    docs = []
    for rel, txt in sorted(files.items()):
        is_readme = rel.lower().endswith("readme.md")
        docs.append(Document(f"{persona}:repo:{key}", txt, {
            "persona": persona, "type": "repo_readme" if is_readme else "repo_code", "project": key,
            "title": f"{key}/{rel}", "path": rel, "date": "", "client_industry": "",
            "skills": sorted(explicit_skills(txt)), "source": f"repo:{key}/{rel}"}))
    return docs


def load_reviews(path: Path, persona: str) -> list[Document]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        out.append(Document(f"{persona}:review:{r['id']}", f"Client review ({r['rating']}/5): {r['text']}", {
            "persona": persona, "type": "review", "project": r["project"], "title": f"Review of {r['project']}",
            "date": r["date"], "client_industry": r["client_industry"], "rating": r["rating"],
            "skills": sorted(explicit_skills(r["text"])), "source": "reviews.jsonl"}))
    return out


def load_proposals(path: Path, persona: str) -> list[Document]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = json.loads(line)
        out.append(Document(f"{persona}:proposal:{p['id']}", p["text"], {
            "persona": persona, "type": "proposal", "project": ",".join(p["cited_projects"]), "title": p["job_title"],
            "date": p["date"], "client_industry": p["client_industry"], "outcome": p["outcome"], "style": p["style"],
            "job_skills": p["job_skills"], "cited_projects": p["cited_projects"], "skills": sorted(explicit_skills(p["text"])),
            "source": "proposals.jsonl"}))
    return out


def load_persona(persona_dir: Path) -> list[Document]:
    pid = persona_dir.name
    docs: list[Document] = []
    if (persona_dir / "cv.pdf").exists():
        docs += load_cv_pdf(persona_dir / "cv.pdf", pid)
    for f in sorted((persona_dir / "case_studies").glob("*.md")):
        docs.append(load_case_study(f, pid))
    for r in sorted((persona_dir / "repos").glob("*")):
        if r.is_dir():
            docs += load_repo(r, pid)
    if (persona_dir / "reviews.jsonl").exists():
        docs += load_reviews(persona_dir / "reviews.jsonl", pid)
    if (persona_dir / "proposals.jsonl").exists():
        docs += load_proposals(persona_dir / "proposals.jsonl", pid)
    # user uploads added through the UI live next to the corpus
    up = persona_dir / "uploads"
    if up.exists():
        for f in sorted(up.glob("*.md")):
            d = load_case_study(f, pid)
            d.meta["source"] = f"upload:{f.name}"
            docs.append(d)
    return docs

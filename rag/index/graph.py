"""Skill graph (V9 GraphRAG-style): skills, projects, industries and outcomes as a graph.

Nodes:  skill:<id>  project:<key>  industry:<name>  item:<item_id>
Edges:  project -[uses w]-> skill  (w = number of independent sources confirming it:
        case study, CV, README, code, semantic match)
        project -> industry ; project -> item ; skill -[won/replied/ignored]-> outcome counts
Answers questions like "have I done X for a client in Y industry?" with a path, not a vibe.
"""
from __future__ import annotations

from collections import defaultdict

from rag.ingest.loaders import Document


class SkillGraph:
    def __init__(self) -> None:
        self.project_skills: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.skill_projects: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.project_industry: dict[str, str] = {}
        self.project_items: dict[str, set[str]] = defaultdict(set)
        self.project_title: dict[str, str] = {}
        self.skill_outcomes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @classmethod
    def build(cls, docs: list[Document], semantic: dict[str, dict[str, float]] | None = None) -> "SkillGraph":
        g = cls()
        for d in docs:
            m = d.meta
            if m["type"] == "proposal":
                for s in m.get("skills", []):
                    g.skill_outcomes[s][m.get("outcome", "ignored")] += 1
                continue
            p = m.get("project")
            if not p:
                continue
            if m["type"] != "review":
                g.project_items[p].add(d.item_id)
            if m.get("client_industry"):
                g.project_industry[p] = m["client_industry"]
            if m["type"] == "case_study":
                g.project_title[p] = m.get("title", p)
            w = {"case_study": 1.0, "cv": 0.8, "repo_code": 1.0, "repo_readme": 0.6, "review": 0.4}.get(m["type"], 0.5)
            for s in m.get("skills", []):
                g._edge(p, s, w)
        for item_id, sk in (semantic or {}).items():
            p = item_id.split(":", 2)[-1]
            for s, sc in sk.items():
                g._edge(p, s, 0.5 * sc)
        return g

    def _edge(self, p: str, s: str, w: float) -> None:
        self.project_skills[p][s] += w
        self.skill_projects[s][p] += w

    def projects_for(self, skills: list[str], industry: str | None = None) -> list[tuple[str, float, list[str]]]:
        """Rank projects by weighted skill coverage; returns (project, score, matched skills)."""
        score: dict[str, float] = defaultdict(float)
        matched: dict[str, list[str]] = defaultdict(list)
        for s in skills:
            for p, w in self.skill_projects.get(s, {}).items():
                score[p] += min(w, 2.0)
                matched[p].append(s)
        if industry:
            for p in score:
                if self.project_industry.get(p, "").lower() == industry.lower():
                    score[p] += 0.75
        return sorted(((p, sc, matched[p]) for p, sc in score.items()), key=lambda x: -x[1])

    def have_i_done(self, skill: str, industry: str | None = None) -> list[dict]:
        out = []
        for p, w in sorted(self.skill_projects.get(skill, {}).items(), key=lambda x: -x[1]):
            ind = self.project_industry.get(p, "")
            if industry and ind.lower() != industry.lower():
                continue
            out.append({"project": p, "title": self.project_title.get(p, p), "industry": ind, "strength": round(w, 2),
                        "items": sorted(self.project_items[p])})
        return out

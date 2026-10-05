"""Lightweight fairness audit on match explanations."""

from __future__ import annotations

PROXY = ("photo", "age", "young", "old", "gender", "male", "female", "nationality", "native")


def audit(rationale: str, required_skills: list[str], mentioned_skills: list[str]) -> dict:
    text = (rationale or "").lower()
    proxies = [p for p in PROXY if p in text]
    req = {s.lower() for s in required_skills}
    got = {s.lower() for s in mentioned_skills}
    coverage = len(req & got) / max(1, len(req))
    return {
        "proxy_terms": proxies,
        "skill_coverage": round(coverage, 2),
        "fairness_pass": not proxies and coverage >= 0.4,
        "notes": "Avoid demographic proxies; score on skills and evidence only." if proxies else "No obvious proxy terms.",
    }

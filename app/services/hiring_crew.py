"""Hiring crew: parser → matcher → interviewer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.llm_client import LLMClient


@dataclass
class CrewResult:
    crew: str = "hiring"
    used_llm: bool = False
    steps: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    questions: list[str] = field(default_factory=list)
    summary: str = ""


class HiringCrew:
    def run(self, resume_text: str, job_text: str) -> CrewResult:
        client = LLMClient()
        used = client.enabled
        if used:
            parsed = client.chat_json_sync(
                "Extract JSON with keys skills (list), years (number), headline (string).",
                resume_text[:6000],
            )
            match = client.chat_json_sync(
                "Return JSON with score 0-1, matched_skills, gaps, rationale.",
                f"JD:\n{job_text[:4000]}\nResume facts:\n{parsed}",
            )
            interview = client.chat_json_sync(
                "Return JSON with questions (list of 5 screening questions).",
                f"Gaps: {match}",
            )
            score = float(match.get("score", 0.5))
            questions = [str(q) for q in interview.get("questions", [])][:5]
            summary = str(match.get("rationale") or parsed)
            steps = [
                {"agent": "parser", "output": parsed},
                {"agent": "matcher", "output": match},
                {"agent": "interviewer", "output": interview},
            ]
        else:
            resume_l = resume_text.lower()
            job_l = job_text.lower()
            tokens = {t for t in job_l.replace(",", " ").split() if len(t) > 3}
            hits = [t for t in tokens if t in resume_l]
            score = min(1.0, len(hits) / max(8, len(tokens) * 0.15))
            questions = [
                "Walk me through a project closest to this role.",
                "Which required skill is your strongest, and how do you prove it?",
                "What gap in the job description would you close first?",
            ]
            parsed = {"headline": resume_text[:120], "overlap": hits[:12]}
            steps = [
                {"agent": "parser", "output": parsed},
                {"agent": "matcher", "output": {"score": score, "matched_skills": hits[:12]}},
                {"agent": "interviewer", "output": {"questions": questions}},
            ]
            summary = f"Heuristic overlap={len(hits)} tokens; score={score:.2f}"
        return CrewResult(used_llm=used, steps=steps, score=score, questions=questions, summary=summary)

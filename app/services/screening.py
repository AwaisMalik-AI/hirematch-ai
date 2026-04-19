"""Screening copilot: summaries, questions, comparisons, outreach drafts."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recruitment import Candidate, JobDescription, OutreachEmail, ScreeningRecommendation, ScreeningResult
from app.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _compact(obj: Any, max_len: int = 6000) -> str:
    s = json.dumps(obj, default=str, ensure_ascii=False)
    return s[:max_len]


class ScreeningService:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()

    async def _load_pair(
        self, db: AsyncSession, candidate_id: int, job_id: int
    ) -> tuple[Candidate, JobDescription]:
        c = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
        j = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
        if c is None or j is None:
            raise ValueError("Candidate or job not found")
        return c, j

    def _fallback_summary(self, candidate: Candidate, job: JobDescription) -> str:
        skills = (candidate.parsed_resume or {}).get("skills") or []
        return (
            f"**{candidate.full_name or candidate.email}** vs **{job.title}** — "
            f"Skills detected: {', '.join(map(str, skills[:12]))}. "
            "Enable LLM_API_KEY for a richer narrative summary."
        )

    async def generate_summary(self, db: AsyncSession, *, candidate_id: int, job_id: int) -> ScreeningResult:
        candidate, job = await self._load_pair(db, candidate_id, job_id)
        if not self._llm.enabled:
            text = self._fallback_summary(candidate, job)
            row = await self._upsert_screening(db, candidate_id, job_id, recruiter_summary=text)
            return row

        system = "You are a senior recruiter. Produce a neutral, evidence-based summary for internal review."
        user = (
            f"Job: {job.title} at {job.company}\nJD excerpt:\n{job.description[:4000]}\n\n"
            f"Candidate: {candidate.full_name} <{candidate.email}>\n"
            f"Parsed resume JSON:\n{_compact(candidate.parsed_resume)}\n"
            'Return JSON {"recruiter_summary": "markdown", "recommendation": one of '
            '"strong_yes","yes","maybe","no","strong_no" or null}'
        )
        try:
            data = await self._llm.chat_json(system, user, temperature=0.25)
        except Exception as e:
            logger.warning("Summary LLM failed: %s", e)
            text = self._fallback_summary(candidate, job)
            return await self._upsert_screening(db, candidate_id, job_id, recruiter_summary=text)

        text = str(data.get("recruiter_summary") or "").strip()
        rec = data.get("recommendation")
        recommendation = None
        if rec:
            try:
                recommendation = ScreeningRecommendation(str(rec))
            except ValueError:
                recommendation = None
        return await self._upsert_screening(
            db,
            candidate_id,
            job_id,
            recruiter_summary=text or self._fallback_summary(candidate, job),
            recommendation=recommendation,
        )

    async def generate_questions(self, db: AsyncSession, *, candidate_id: int, job_id: int) -> ScreeningResult:
        candidate, job = await self._load_pair(db, candidate_id, job_id)
        gaps: list[Any] = []
        # Pull gaps from latest match if stored in DB — optional
        from app.models.recruitment import MatchResult

        mr = (
            await db.execute(
                select(MatchResult).where(
                    MatchResult.candidate_id == candidate_id,
                    MatchResult.job_id == job_id,
                )
            )
        ).scalar_one_or_none()
        if mr and isinstance(mr.skill_gaps, list):
            gaps = mr.skill_gaps

        if not self._llm.enabled:
            qs = [
                f"Walk me through a recent project using {gaps[0]}." if gaps else "Describe a complex problem you owned end-to-end.",
                "How does this role align with your next career step?",
                "What constraints have you operated under (team size, deadlines, budget)?",
            ]
            return await self._upsert_screening(db, candidate_id, job_id, screening_questions=qs)

        system = "You write sharp, fair phone-screen questions tied to skill gaps and role needs."
        user = (
            f"Job: {job.title}\nMust-haves context:\n{_compact(job.requirements)}\n\n"
            f"Candidate parsed resume:\n{_compact(candidate.parsed_resume)}\n"
            f"Known skill gaps: {gaps}\n"
            'Return JSON {"questions": ["...", "...", "..."]} with 5-8 questions.'
        )
        try:
            data = await self._llm.chat_json(system, user, temperature=0.35)
        except Exception as e:
            logger.warning("Questions LLM failed: %s", e)
            qs = [
                "What is the hardest technical tradeoff you navigated in the last year?",
                "How do you validate quality before shipping?",
            ]
            return await self._upsert_screening(db, candidate_id, job_id, screening_questions=qs)

        qs = list(data.get("questions") or [])
        qs = [str(q).strip() for q in qs if str(q).strip()]
        return await self._upsert_screening(db, candidate_id, job_id, screening_questions=qs)

    async def compare_candidates(
        self, db: AsyncSession, *, candidate_ids: list[int], job_id: int
    ) -> tuple[str, dict[str, Any]]:
        job = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
        if job is None:
            raise ValueError("Job not found")
        candidates: list[Candidate] = []
        for cid in candidate_ids:
            c = (await db.execute(select(Candidate).where(Candidate.id == cid))).scalar_one_or_none()
            if c:
                candidates.append(c)
        if len(candidates) < 2:
            raise ValueError("Need at least two valid candidates")

        from app.models.recruitment import MatchResult

        scores: dict[int, float | None] = {}
        for c in candidates:
            mr = (
                await db.execute(
                    select(MatchResult).where(
                        MatchResult.candidate_id == c.id,
                        MatchResult.job_id == job_id,
                    )
                )
            ).scalar_one_or_none()
            scores[c.id] = mr.overall_score if mr else None

        if not self._llm.enabled:
            lines = [
                f"| Candidate | Match score |\n|---|---|",
            ]
            for c in candidates:
                lines.append(f"| {c.full_name or c.email} | {scores.get(c.id)} |")
            md = "\n".join(lines) + "\n\n_Enable LLM for narrative comparison._"
            return md, {"scores": scores}

        system = "You compare candidates fairly for a hiring committee. Markdown table + narrative."
        blocks = []
        for c in candidates:
            blocks.append(
                {
                    "id": c.id,
                    "name": c.full_name,
                    "email": c.email,
                    "status": c.status.value,
                    "parsed_resume": c.parsed_resume,
                    "match_overall": scores.get(c.id),
                }
            )
        user = (
            f"Role: {job.title}\nCompany: {job.company}\nJD:\n{job.description[:3000]}\n\n"
            f"Candidates:\n{json.dumps(blocks, default=str)[:12000]}\n"
            'Return JSON {"comparison_markdown": "...", "structured": {}}'
        )
        data = await self._llm.chat_json(system, user, temperature=0.25)
        md = str(data.get("comparison_markdown") or "").strip()
        struct = data.get("structured") if isinstance(data.get("structured"), dict) else {}
        if not md:
            md = "Comparison unavailable."
        return md, struct

    async def draft_outreach(self, db: AsyncSession, *, candidate_id: int, job_id: int) -> OutreachEmail:
        candidate, job = await self._load_pair(db, candidate_id, job_id)
        subject = f"Opportunity: {job.title} at {job.company}"
        body = (
            f"Hi {candidate.full_name or 'there'},\n\n"
            f"We're hiring for {job.title}. Based on your background, "
            "we'd love to share more detail.\n\n"
            "Best,\nRecruiting Team"
        )
        if self._llm.enabled:
            system = "You write concise, respectful recruiter outreach emails. No overpromising."
            user = (
                f"Job title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
                f"Candidate name: {candidate.full_name}\nSummary:\n{_compact(candidate.parsed_resume, 3000)}\n"
                'Return JSON {"subject": "...", "body": "plain text email body"}.'
            )
            try:
                data = await self._llm.chat_json(system, user, temperature=0.4)
                subject = str(data.get("subject") or subject).strip()
                body = str(data.get("body") or body).strip()
            except Exception as e:
                logger.warning("Outreach LLM failed: %s", e)

        row = OutreachEmail(
            candidate_id=candidate_id,
            job_id=job_id,
            subject=subject,
            body=body,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        return row

    async def _upsert_screening(
        self,
        db: AsyncSession,
        candidate_id: int,
        job_id: int,
        *,
        recruiter_summary: str | None = None,
        screening_questions: list[str] | None = None,
        comparison_notes: str | None = None,
        recommendation: ScreeningRecommendation | None = None,
    ) -> ScreeningResult:
        existing = (
            await db.execute(
                select(ScreeningResult).where(
                    ScreeningResult.candidate_id == candidate_id,
                    ScreeningResult.job_id == job_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            row = ScreeningResult(
                candidate_id=candidate_id,
                job_id=job_id,
                recruiter_summary=recruiter_summary,
                screening_questions=screening_questions or [],
                comparison_notes=comparison_notes,
                recommendation=recommendation,
            )
            db.add(row)
        else:
            if recruiter_summary is not None:
                existing.recruiter_summary = recruiter_summary
            if screening_questions is not None:
                existing.screening_questions = screening_questions
            if comparison_notes is not None:
                existing.comparison_notes = comparison_notes
            if recommendation is not None:
                existing.recommendation = recommendation
            row = existing
        await db.flush()
        await db.refresh(row)
        return row

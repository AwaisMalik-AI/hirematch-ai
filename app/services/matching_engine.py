"""Semantic + rule-based matching with explainable scoring."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.models.recruitment import Candidate, JobDescription, MatchResult
from app.services.llm_client import LLMClient, cosine_similarity, normalize_skills

logger = logging.getLogger(__name__)

_SENIORITY_YEARS = {
    "intern": 0.0,
    "junior": 1.0,
    "mid": 3.0,
    "middle": 3.0,
    "senior": 5.0,
    "lead": 6.0,
    "staff": 7.0,
    "principal": 8.0,
}


def _job_skill_lists(job: JobDescription) -> tuple[set[str], set[str]]:
    ps = job.parsed_skills
    if isinstance(ps, list):
        required = set(normalize_skills([str(x) for x in ps]))
        preferred: set[str] = set()
    elif isinstance(ps, dict):
        req_list = ps.get("required") or ps.get("must_have") or []
        pref_list = ps.get("preferred") or ps.get("nice_to_have") or []
        if isinstance(req_list, str):
            req_list = [req_list]
        if isinstance(pref_list, str):
            pref_list = [pref_list]
        required = set(normalize_skills([str(x) for x in req_list]))
        preferred = set(normalize_skills([str(x) for x in pref_list]))
    else:
        required, preferred = set(), set()
    # Also pull from requirements JSON strings
    req_obj = job.requirements or {}
    for k in ("must_have", "required", "skills"):
        v = req_obj.get(k)
        if isinstance(v, list):
            required |= set(normalize_skills([str(x) for x in v]))
    pref_obj = job.preferred or {}
    for k in ("nice_to_have", "preferred", "skills"):
        v = pref_obj.get(k)
        if isinstance(v, list):
            preferred |= set(normalize_skills([str(x) for x in v]))
    return required, preferred


def _candidate_skills(parsed: dict[str, Any]) -> set[str]:
    skills = parsed.get("skills") or []
    if not isinstance(skills, list):
        return set()
    return set(normalize_skills([str(x) for x in skills]))


def _education_level(parsed: dict[str, Any]) -> float:
    edu = parsed.get("education") or []
    if not isinstance(edu, list) or not edu:
        return 0.4
    text = " ".join(str(e).lower() for e in edu)
    if "phd" in text or "doctor" in text:
        return 1.0
    if "master" in text or "mba" in text:
        return 0.85
    if "bachelor" in text or " b.s" in text or " bs " in text or "undergraduate" in text:
        return 0.7
    return 0.55


def _job_education_expectation(job: JobDescription) -> float:
    blob = f"{job.description} {job.requirements}".lower()
    if "phd" in blob:
        return 1.0
    if "master" in blob or "mba" in blob:
        return 0.85
    if "bachelor" in blob or "degree" in blob:
        return 0.7
    return 0.55


def _experience_score(candidate_years: float | None, job: JobDescription) -> tuple[float, dict[str, Any]]:
    min_y = job.min_experience_years
    sen = (job.seniority_level or "").lower()
    expected = float(min_y) if min_y is not None else _SENIORITY_YEARS.get(sen, 3.0)
    cy = float(candidate_years) if candidate_years is not None else 0.0
    if expected <= 0:
        score = 1.0 if cy >= 0 else 0.0
    else:
        ratio = cy / expected
        if ratio >= 1.0:
            score = 1.0
        elif ratio >= 0.7:
            score = 0.7 + 0.3 * ((ratio - 0.7) / 0.3)
        else:
            score = max(0.0, ratio / 0.7 * 0.7)
    detail = {
        "candidate_years": cy,
        "expected_years": expected,
        "seniority_level": job.seniority_level,
        "job_min_experience_years": job.min_experience_years,
    }
    return float(score), detail


def _skill_match_score(
    cskills: set[str], required: set[str], preferred: set[str]
) -> tuple[float, list[str], list[str]]:
    if not required and not preferred:
        return 1.0, [], list(cskills)[:12]

    req_hit = len(cskills & required)
    req_miss = list(sorted(required - cskills))
    pref_hit = len(cskills & preferred)
    pref_only = preferred - required
    pref_miss = list(sorted(pref_only - cskills))

    req_score = 1.0 if not required else req_hit / max(1, len(required))
    pref_score = 1.0 if not pref_only else pref_hit / max(1, len(pref_only))
    combined = 0.75 * req_score + 0.25 * pref_score

    strong = list(sorted((cskills & required) | (cskills & preferred)))[:20]
    gaps = req_miss[:20]
    if len(gaps) < 10:
        gaps = list(dict.fromkeys(gaps + pref_miss))[:20]
    return float(max(0.0, min(1.0, combined))), gaps, strong


class MatchingEngine:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()
        self._settings = get_settings()

    async def _embed_pair(self, candidate_summary: str, jd_blob: str) -> tuple[float, dict[str, Any]]:
        cand_text = (candidate_summary or "")[:8000]
        job_text = jd_blob[:8000]
        vecs = await self._llm.embed_texts([cand_text, job_text])
        if len(vecs) != 2:
            return 0.0, {"note": "embedding_failed"}
        sim = cosine_similarity(vecs[0], vecs[1])
        return sim, {"method": "openai" if self._llm.enabled else "fallback_char_embedding"}

    async def match(
        self,
        db: AsyncSession,
        *,
        candidate_id: int,
        job_id: int,
        explain: bool = True,
    ) -> MatchResult:
        c_res = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
        candidate = c_res.scalar_one_or_none()
        if candidate is None:
            raise ValueError("Candidate not found")
        j_res = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
        job = j_res.scalar_one_or_none()
        if job is None:
            raise ValueError("Job not found")

        parsed = candidate.parsed_resume or {}
        summary = str(parsed.get("summary") or "") or (candidate.full_name or "")
        jd_blob = f"{job.title}\n{job.description}\n{job.requirements}\n{job.preferred}"

        semantic, sem_detail = await self._embed_pair(summary, jd_blob)

        cskills = _candidate_skills(parsed)
        required, preferred = _job_skill_lists(job)
        skill_score, gaps, strong = _skill_match_score(cskills, required, preferred)

        cy = parsed.get("total_years_experience")
        cy_f = float(cy) if cy is not None else None
        exp_score, exp_detail = _experience_score(cy_f, job)

        edu_c = _education_level(parsed)
        edu_j = _job_education_expectation(job)
        edu_score = 1.0 - min(1.0, abs(edu_c - edu_j))
        edu_detail = {"candidate_education_score": edu_c, "job_education_expectation": edu_j}

        w = self._settings
        overall = (
            w.match_weight_semantic * semantic
            + w.match_weight_skills * skill_score
            + w.match_weight_experience * exp_score
            + w.match_weight_education * edu_score
        )

        breakdown = {
            "weights": {
                "semantic": w.match_weight_semantic,
                "skills": w.match_weight_skills,
                "experience": w.match_weight_experience,
                "education": w.match_weight_education,
            },
            "semantic_detail": sem_detail,
            "experience_detail": exp_detail,
            "education_detail": edu_detail,
            "required_skills": sorted(required),
            "preferred_skills": sorted(preferred),
            "candidate_skills_sample": sorted(cskills)[:40],
        }

        explanation = None
        if explain and self._llm.enabled:
            try:
                explanation = await self.explain_match_dict(
                    candidate_name=candidate.full_name or candidate.email,
                    job_title=job.title,
                    overall=overall,
                    semantic=semantic,
                    skill_score=skill_score,
                    experience_score=exp_score,
                    education_score=edu_score,
                    gaps=gaps,
                    strong=strong,
                )
            except Exception as e:
                logger.warning("Explain match LLM failed: %s", e)

        existing = await db.execute(
            select(MatchResult).where(
                MatchResult.candidate_id == candidate_id,
                MatchResult.job_id == job_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row is None:
            row = MatchResult(
                candidate_id=candidate_id,
                job_id=job_id,
                overall_score=overall,
                semantic_score=semantic,
                skill_match_score=skill_score,
                experience_score=exp_score,
                education_score=edu_score,
                scoring_breakdown=breakdown,
                skill_gaps=gaps,
                strong_matches=strong,
                explanation=explanation,
            )
            db.add(row)
        else:
            row.overall_score = overall
            row.semantic_score = semantic
            row.skill_match_score = skill_score
            row.experience_score = exp_score
            row.education_score = edu_score
            row.scoring_breakdown = breakdown
            row.skill_gaps = gaps
            row.strong_matches = strong
            row.explanation = explanation if explanation is not None else row.explanation

        await db.flush()
        await db.refresh(row)
        return row

    async def explain_match(self, db: AsyncSession, match_result: MatchResult) -> str:
        cand_res = await db.execute(select(Candidate).where(Candidate.id == match_result.candidate_id))
        candidate = cand_res.scalar_one()
        job_res = await db.execute(select(JobDescription).where(JobDescription.id == match_result.job_id))
        job = job_res.scalar_one()
        gaps = match_result.skill_gaps if isinstance(match_result.skill_gaps, list) else []
        strong = match_result.strong_matches if isinstance(match_result.strong_matches, list) else []
        text = await self.explain_match_dict(
            candidate_name=candidate.full_name or candidate.email,
            job_title=job.title,
            overall=match_result.overall_score,
            semantic=match_result.semantic_score,
            skill_score=match_result.skill_match_score,
            experience_score=match_result.experience_score,
            education_score=match_result.education_score,
            gaps=list(gaps),
            strong=list(strong),
        )
        match_result.explanation = text
        await db.flush()
        return text

    async def explain_match_dict(
        self,
        *,
        candidate_name: str,
        job_title: str,
        overall: float,
        semantic: float,
        skill_score: float,
        experience_score: float,
        education_score: float,
        gaps: list[str],
        strong: list[str],
    ) -> str:
        system = (
            "You are an expert recruiter. Write a concise, factual explanation of a candidate-job match. "
            "No fluff, no discriminatory language. Reference scores and skill gaps constructively."
        )
        user = (
            f"Candidate: {candidate_name}\nRole: {job_title}\n"
            f"Overall: {overall:.3f}\nSemantic: {semantic:.3f}\n"
            f"Skills: {skill_score:.3f}\nExperience: {experience_score:.3f}\n"
            f"Education fit: {education_score:.3f}\n"
            f"Strong matches: {strong[:15]}\nSkill gaps: {gaps[:15]}\n"
            "Produce 1 short paragraph plus 3 bullet points."
        )
        data = await self._llm.chat_json(
            system,
            user + '\nReturn JSON {"explanation": "markdown string"}.',
            temperature=0.3,
        )
        return str(data.get("explanation") or data.get("text") or "").strip() or (
            f"Match strength **{overall:.0%}** — review skill gaps: {', '.join(gaps[:5]) or 'none noted'}."
        )

    async def batch_match(self, db: AsyncSession, *, job_id: int) -> list[int]:
        j_res = await db.execute(select(JobDescription).where(JobDescription.id == job_id))
        job = j_res.scalar_one_or_none()
        if job is None:
            raise ValueError("Job not found")

        from app.models.recruitment import CandidateStatus

        c_res = await db.execute(
            select(Candidate).where(
                Candidate.status.not_in([CandidateStatus.REJECTED, CandidateStatus.HIRED])
            )
        )
        candidates = c_res.scalars().all()
        ids: list[int] = []
        for c in candidates:
            mr = await self.match(db, candidate_id=c.id, job_id=job_id, explain=False)
            ids.append(mr.id)
        return ids

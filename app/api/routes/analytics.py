"""Pipeline analytics: funnel stats and top matches per job."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_roles
from app.models.recruitment import Candidate, CandidateStatus, JobDescription, MatchResult, ScreeningResult
from app.models.user import User, UserRole
from app.schemas.analytics import (
    JobPipelineStats,
    PipelineOverview,
    StageCount,
    TopCandidateItem,
    TopCandidatesResponse,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/analytics", tags=["analytics"])

_reader = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER))


@router.get("/pipeline", response_model=PipelineOverview)
async def pipeline_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _reader],
):
    total_jobs = (await db.execute(select(func.count()).select_from(JobDescription))).scalar_one()
    active_jobs = (
        await db.execute(select(func.count()).select_from(JobDescription).where(JobDescription.is_active.is_(True)))
    ).scalar_one()
    total_candidates = (await db.execute(select(func.count()).select_from(Candidate))).scalar_one()

    jobs_res = await db.execute(select(JobDescription).order_by(JobDescription.created_at.desc()).limit(100))
    jobs = list(jobs_res.scalars().all())
    stats: list[JobPipelineStats] = []

    for job in jobs:
        counts_map: dict[str, int] = {st.value: 0 for st in CandidateStatus}
        status_rows = await db.execute(
            select(Candidate.status, func.count())
            .join(MatchResult, MatchResult.candidate_id == Candidate.id)
            .where(MatchResult.job_id == job.id)
            .group_by(Candidate.status)
        )
        for st, cnt in status_rows.all():
            counts_map[st.value] = int(cnt)
        counts = [StageCount(stage=k, count=v) for k, v in counts_map.items()]

        match_count = (
            await db.execute(
                select(func.count()).select_from(MatchResult).where(MatchResult.job_id == job.id)
            )
        ).scalar_one()
        avg = (
            await db.execute(
                select(func.avg(MatchResult.overall_score)).where(MatchResult.job_id == job.id)
            )
        ).scalar_one()
        screened = (
            await db.execute(
                select(func.count()).select_from(ScreeningResult).where(ScreeningResult.job_id == job.id)
            )
        ).scalar_one()

        stats.append(
            JobPipelineStats(
                job_id=job.id,
                job_title=job.title,
                candidate_counts_by_status=counts,
                match_count=int(match_count),
                avg_overall_score=float(avg) if avg is not None else None,
                screened_count=int(screened),
            )
        )

    await write_audit(
        db,
        user_id=current.id,
        action="analytics.pipeline",
        entity_type="analytics",
        entity_id=None,
    )
    return PipelineOverview(
        total_jobs=int(total_jobs),
        active_jobs=int(active_jobs),
        total_candidates=int(total_candidates),
        jobs=stats,
    )


@router.get("/jobs/{job_id}/top-candidates", response_model=TopCandidatesResponse)
async def top_candidates_for_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _reader],
    n: int = 10,
):
    job = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    stmt = (
        select(MatchResult, Candidate)
        .join(Candidate, Candidate.id == MatchResult.candidate_id)
        .where(MatchResult.job_id == job_id)
        .order_by(MatchResult.overall_score.desc())
        .limit(min(n, 50))
    )
    res = await db.execute(stmt)
    items: list[TopCandidateItem] = []
    for mr, cand in res.all():
        items.append(
            TopCandidateItem(
                candidate_id=cand.id,
                full_name=cand.full_name,
                email=cand.email,
                overall_score=mr.overall_score,
                match_result_id=mr.id,
            )
        )

    await write_audit(
        db,
        user_id=current.id,
        action="analytics.top_candidates",
        entity_type="job_description",
        entity_id=job_id,
        details={"n": n},
    )
    return TopCandidatesResponse(job_id=job_id, top_n=len(items), items=items)

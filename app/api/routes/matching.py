"""Matching: single match, batch, fetch results, explain."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_roles
from app.models.recruitment import JobDescription, MatchResult
from app.models.user import User, UserRole
from app.schemas.matching import (
    BatchMatchResponse,
    ExplainMatchRequest,
    ExplainMatchResponse,
    MatchResultRead,
    MatchRunRequest,
)
from app.services.audit import write_audit
from app.services.matching_engine import MatchingEngine
from app.tasks.processing_tasks import batch_match_task

router = APIRouter(prefix="/matching", tags=["matching"])

_writer = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER))


@router.post("/run", response_model=MatchResultRead)
async def run_match(
    body: MatchRunRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    engine = MatchingEngine()
    try:
        row = await engine.match(
            db,
            candidate_id=body.candidate_id,
            job_id=body.job_id,
            explain=body.explain,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await write_audit(
        db,
        user_id=current.id,
        action="matching.run",
        entity_type="match_result",
        entity_id=row.id,
        details={"candidate_id": body.candidate_id, "job_id": body.job_id},
    )
    return row


@router.post("/batch", response_model=BatchMatchResponse)
async def batch_match(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
    async_run: bool = True,
):
    job = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if async_run:
        try:
            batch_match_task.delay(job_id)
            await write_audit(
                db,
                user_id=current.id,
                action="matching.batch_queued",
                entity_type="job_description",
                entity_id=job_id,
            )
            return BatchMatchResponse(job_id=job_id, processed=0, match_ids=[])
        except Exception:
            pass

    engine = MatchingEngine()
    ids = await engine.batch_match(db, job_id=job_id)
    await write_audit(
        db,
        user_id=current.id,
        action="matching.batch",
        entity_type="job_description",
        entity_id=job_id,
        details={"count": len(ids)},
    )
    return BatchMatchResponse(job_id=job_id, processed=len(ids), match_ids=ids)


@router.get("/job/{job_id}", response_model=list[MatchResultRead])
async def matches_for_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
    min_score: float | None = None,
):
    stmt = select(MatchResult).where(MatchResult.job_id == job_id).order_by(MatchResult.overall_score.desc())
    if min_score is not None:
        stmt = stmt.where(MatchResult.overall_score >= min_score)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/candidate/{candidate_id}", response_model=list[MatchResultRead])
async def matches_for_candidate(
    candidate_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
):
    res = await db.execute(
        select(MatchResult)
        .where(MatchResult.candidate_id == candidate_id)
        .order_by(MatchResult.overall_score.desc())
    )
    return list(res.scalars().all())


@router.post("/explain", response_model=ExplainMatchResponse)
async def explain_match(
    body: ExplainMatchRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = (await db.execute(select(MatchResult).where(MatchResult.id == body.match_result_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Match result not found")
    engine = MatchingEngine()
    try:
        text = await engine.explain_match(db, row)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Explanation failed: {e}") from e
    await write_audit(
        db,
        user_id=current.id,
        action="matching.explain",
        entity_type="match_result",
        entity_id=row.id,
    )
    return ExplainMatchResponse(match_result_id=row.id, explanation=text)

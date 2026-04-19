"""Screening copilot: summaries, questions, comparison, outreach drafts."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_roles
from app.models.user import User, UserRole
from app.schemas.screening import (
    CandidateCompareRequest,
    CandidateCompareResponse,
    OutreachDraftResponse,
    ScreeningQuestionsResponse,
    ScreeningSummaryResponse,
)
from app.services.audit import write_audit
from app.services.screening import ScreeningService

router = APIRouter(prefix="/screening", tags=["screening"])

_writer = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER))


@router.post("/summary", response_model=ScreeningSummaryResponse)
async def screening_summary(
    candidate_id: int,
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    svc = ScreeningService()
    try:
        row = await svc.generate_summary(db, candidate_id=candidate_id, job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await write_audit(
        db,
        user_id=current.id,
        action="screening.summary",
        entity_type="screening_result",
        entity_id=row.id,
        details={"candidate_id": candidate_id, "job_id": job_id},
    )
    summary = row.recruiter_summary or ""
    return ScreeningSummaryResponse(
        candidate_id=candidate_id,
        job_id=job_id,
        recruiter_summary=summary,
        screening_result_id=row.id,
    )


@router.post("/questions", response_model=ScreeningQuestionsResponse)
async def screening_questions(
    candidate_id: int,
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    svc = ScreeningService()
    try:
        row = await svc.generate_questions(db, candidate_id=candidate_id, job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await write_audit(
        db,
        user_id=current.id,
        action="screening.questions",
        entity_type="screening_result",
        entity_id=row.id,
    )
    qs = row.screening_questions if isinstance(row.screening_questions, list) else []
    qs_str = [str(x) for x in qs]
    return ScreeningQuestionsResponse(
        candidate_id=candidate_id,
        job_id=job_id,
        screening_questions=qs_str,
        screening_result_id=row.id,
    )


@router.post("/compare", response_model=CandidateCompareResponse)
async def compare_candidates(
    body: CandidateCompareRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    svc = ScreeningService()
    try:
        md, structured = await svc.compare_candidates(
            db, candidate_ids=body.candidate_ids, job_id=body.job_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await write_audit(
        db,
        user_id=current.id,
        action="screening.compare",
        entity_type="job_description",
        entity_id=body.job_id,
        details={"candidate_ids": body.candidate_ids},
    )
    return CandidateCompareResponse(job_id=body.job_id, comparison_markdown=md, structured=structured)


@router.post("/outreach", response_model=OutreachDraftResponse)
async def draft_outreach(
    candidate_id: int,
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    svc = ScreeningService()
    try:
        row = await svc.draft_outreach(db, candidate_id=candidate_id, job_id=job_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await write_audit(
        db,
        user_id=current.id,
        action="screening.outreach_draft",
        entity_type="outreach_email",
        entity_id=row.id,
    )
    return OutreachDraftResponse(
        candidate_id=candidate_id,
        job_id=job_id,
        subject=row.subject,
        body=row.body,
        outreach_email_id=row.id,
    )

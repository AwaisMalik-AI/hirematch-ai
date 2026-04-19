"""Job descriptions: CRUD and JD parsing."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_roles
from app.models.recruitment import JobDescription
from app.models.user import User, UserRole
from app.schemas.jobs import JobCreate, JobParseRequest, JobRead, JobUpdate, ParsedJDOut
from app.services.audit import write_audit
from app.services.jd_parser import JDParser

router = APIRouter(prefix="/jobs", tags=["jobs"])

_writer = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER))


@router.get("", response_model=list[JobRead])
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
    active_only: bool = False,
):
    q = select(JobDescription).order_by(JobDescription.created_at.desc())
    if active_only:
        q = q.where(JobDescription.is_active.is_(True))
    res = await db.execute(q)
    return list(res.scalars().all())


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = JobDescription(
        title=body.title,
        company=body.company,
        department=body.department,
        description=body.description,
        requirements=body.requirements,
        preferred=body.preferred,
        location=body.location,
        seniority_level=body.seniority_level,
        salary_range=body.salary_range,
        employment_type=body.employment_type,
        parsed_skills=body.parsed_skills,
        min_experience_years=body.min_experience_years,
        is_active=body.is_active,
        created_by_id=current.id,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        user_id=current.id,
        action="job.create",
        entity_type="job_description",
        entity_id=row.id,
    )
    return row


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
):
    row = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: int,
    body: JobUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    await write_audit(
        db,
        user_id=current.id,
        action="job.update",
        entity_type="job_description",
        entity_id=row.id,
        details={"patch": data},
    )
    return row


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = (await db.execute(select(JobDescription).where(JobDescription.id == job_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await db.execute(delete(JobDescription).where(JobDescription.id == job_id))
    await write_audit(
        db,
        user_id=current.id,
        action="job.delete",
        entity_type="job_description",
        entity_id=job_id,
    )


@router.post("/parse", response_model=ParsedJDOut)
async def parse_jd(
    body: JobParseRequest,
    _: Annotated[User, _writer],
):
    parser = JDParser()
    raw = await parser.parse(body.text)
    return ParsedJDOut(
        requirements=raw.get("requirements") or {},
        preferred=raw.get("preferred") or {},
        parsed_skills=list(raw.get("parsed_skills") or []),
        min_experience_years=raw.get("min_experience_years"),
        seniority_level=raw.get("seniority_level"),
        title_suggestion=raw.get("title_suggestion"),
        confidence=dict(raw.get("confidence") or {}),
    )

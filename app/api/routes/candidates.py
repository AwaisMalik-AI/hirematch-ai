"""Candidates: resume upload, CRUD, search."""

import os
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import cast, delete, or_, select, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db, require_roles
from app.models.recruitment import Candidate
from app.models.user import User, UserRole
from app.schemas.candidates import (
    CandidateCreate,
    CandidateRead,
    CandidateUpdate,
    ResumeUploadResponse,
)
from app.services.audit import write_audit
from app.services.resume_parser import ResumeParser
from app.tasks.processing_tasks import parse_resume_task

router = APIRouter(prefix="/candidates", tags=["candidates"])

_writer = Depends(require_roles(UserRole.ADMIN, UserRole.RECRUITER, UserRole.HIRING_MANAGER))


def _storage_dir() -> Path:
    p = Path(get_settings().resume_storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.get("/search", response_model=list[CandidateRead])
async def search_candidates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
    q: str | None = None,
    status_filter: str | None = None,
    skill: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    stmt = select(Candidate).order_by(Candidate.created_at.desc()).offset(skip).limit(min(limit, 200))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Candidate.full_name.ilike(like), Candidate.email.ilike(like)))
    if status_filter:
        try:
            from app.models.recruitment import CandidateStatus

            stmt = stmt.where(Candidate.status == CandidateStatus(status_filter))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status") from None
    if skill:
        stmt = stmt.where(cast(Candidate.parsed_resume, String).ilike(f"%{skill.lower()}%"))
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post("", response_model=CandidateRead, status_code=status.HTTP_201_CREATED)
async def create_candidate(
    body: CandidateCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    existing = (await db.execute(select(Candidate).where(Candidate.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Candidate email already exists")
    row = Candidate(
        email=body.email,
        full_name=body.full_name,
        phone=body.phone,
        source=body.source,
        status=body.status,
        parsed_resume=body.parsed_resume,
    )
    db.add(row)
    await db.flush()
    await write_audit(
        db,
        user_id=current.id,
        action="candidate.create",
        entity_type="candidate",
        entity_id=row.id,
    )
    return row


@router.post("/upload", response_model=ResumeUploadResponse)
async def upload_resume(
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
    file: UploadFile = File(...),
    email: str = Form(...),
    full_name: str | None = Form(None),
    source: str | None = Form(None),
    async_parse: bool = Form(True),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")

    cand = (await db.execute(select(Candidate).where(Candidate.email == email))).scalar_one_or_none()
    if cand is None:
        cand = Candidate(email=email, full_name=full_name, source=source, parsed_resume={})
        db.add(cand)
        await db.flush()
    ext = Path(file.filename or "resume").suffix or ".bin"
    fname = f"{cand.id}_{uuid.uuid4().hex}{ext}"
    path = _storage_dir() / fname
    path.write_bytes(raw)
    cand.resume_path = str(path)
    cand.full_name = full_name or cand.full_name
    cand.source = source or cand.source
    await db.flush()

    task_id: str | None = None
    if async_parse:
        try:
            async_r = parse_resume_task.delay(cand.id)
            task_id = async_r.id
        except Exception:
            parser = ResumeParser()
            parsed = await parser.parse(raw, file.content_type, filename=file.filename)
            cand.parsed_resume = parsed
            await db.flush()
    else:
        parser = ResumeParser()
        parsed = await parser.parse(raw, file.content_type, filename=file.filename)
        cand.parsed_resume = parsed
        await db.flush()

    await write_audit(
        db,
        user_id=current.id,
        action="candidate.upload_resume",
        entity_type="candidate",
        entity_id=cand.id,
        details={"async": async_parse, "task_id": task_id},
    )
    return ResumeUploadResponse(candidate_id=cand.id, resume_path=str(path), task_id=task_id)


@router.get("", response_model=list[CandidateRead])
async def list_candidates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(Candidate).order_by(Candidate.created_at.desc()).offset(skip).limit(min(limit, 200))
    )
    return list(res.scalars().all())


@router.get("/{candidate_id}", response_model=CandidateRead)
async def get_candidate(
    candidate_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, _writer],
):
    row = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row


@router.patch("/{candidate_id}", response_model=CandidateRead)
async def update_candidate(
    candidate_id: int,
    body: CandidateUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.flush()
    await write_audit(
        db,
        user_id=current.id,
        action="candidate.update",
        entity_type="candidate",
        entity_id=row.id,
        details={"patch": list(data.keys())},
    )
    return row


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_candidate(
    candidate_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, _writer],
):
    row = (await db.execute(select(Candidate).where(Candidate.id == candidate_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if row.resume_path and os.path.isfile(row.resume_path):
        try:
            os.remove(row.resume_path)
        except OSError:
            pass
    await db.execute(delete(Candidate).where(Candidate.id == candidate_id))
    await write_audit(
        db,
        user_id=current.id,
        action="candidate.delete",
        entity_type="candidate",
        entity_id=candidate_id,
    )

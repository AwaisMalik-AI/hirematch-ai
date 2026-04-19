"""Background jobs: resume parsing and batch matching."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.recruitment import Candidate
from app.services.matching_engine import MatchingEngine
from app.services.resume_parser import ResumeParser
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _parse_resume_async(candidate_id: int) -> None:
    async with AsyncSessionLocal() as session:
        try:
            cand = (
                await session.execute(select(Candidate).where(Candidate.id == candidate_id))
            ).scalar_one_or_none()
            if cand is None or not cand.resume_path:
                logger.warning("parse_resume_task: candidate %s missing or no path", candidate_id)
                return
            path = Path(cand.resume_path)
            if not path.is_file():
                logger.warning("parse_resume_task: file missing %s", path)
                return
            raw = path.read_bytes()
            parser = ResumeParser()
            suffix = path.suffix.lower()
            ct = "application/pdf" if suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            parsed = await parser.parse(raw, ct, filename=path.name)
            cand.parsed_resume = parsed
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("parse_resume_task failed for candidate %s", candidate_id)
            raise


async def _batch_match_async(job_id: int) -> list[int]:
    async with AsyncSessionLocal() as session:
        try:
            engine = MatchingEngine()
            ids = await engine.batch_match(session, job_id=job_id)
            await session.commit()
            return ids
        except Exception:
            await session.rollback()
            logger.exception("batch_match_task failed for job %s", job_id)
            raise


@celery_app.task(name="hirematch.parse_resume")
def parse_resume_task(candidate_id: int) -> str:
    asyncio.run(_parse_resume_async(candidate_id))
    return "ok"


@celery_app.task(name="hirematch.batch_match")
def batch_match_task(job_id: int) -> list[int]:
    return asyncio.run(_batch_match_async(job_id))

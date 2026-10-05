from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.hiring_crew import HiringCrew
from app.tasks.crew_tasks import run_hiring_crew_task

router = APIRouter(prefix="/crews", tags=["crews"])


class HiringCrewRequest(BaseModel):
    resume_text: str = Field(..., min_length=20)
    job_text: str = Field(..., min_length=20)
    async_run: bool = False


class HiringCrewResponse(BaseModel):
    crew: str
    used_llm: bool
    steps: list[dict[str, Any]]
    score: float
    questions: list[str]
    summary: str
    task_id: str | None = None


@router.post("/hiring", response_model=HiringCrewResponse)
async def run_hiring_crew(body: HiringCrewRequest, _: CurrentUser) -> HiringCrewResponse:
    if body.async_run:
        task = run_hiring_crew_task.delay(body.resume_text, body.job_text)
        return HiringCrewResponse(
            crew="hiring",
            used_llm=False,
            steps=[],
            score=0.0,
            questions=[],
            summary="queued",
            task_id=task.id,
        )
    result = HiringCrew().run(body.resume_text, body.job_text)
    return HiringCrewResponse(
        crew=result.crew,
        used_llm=result.used_llm,
        steps=result.steps,
        score=result.score,
        questions=result.questions,
        summary=result.summary,
    )

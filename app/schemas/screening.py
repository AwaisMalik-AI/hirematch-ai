from typing import Any

from pydantic import BaseModel, Field

from app.models.recruitment import ScreeningRecommendation


class ScreeningSummaryResponse(BaseModel):
    candidate_id: int
    job_id: int
    recruiter_summary: str
    screening_result_id: int | None = None


class ScreeningQuestionsResponse(BaseModel):
    candidate_id: int
    job_id: int
    screening_questions: list[str]
    screening_result_id: int | None = None


class CandidateCompareRequest(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=2, max_length=20)
    job_id: int


class CandidateCompareResponse(BaseModel):
    job_id: int
    comparison_markdown: str
    structured: dict[str, Any] = Field(default_factory=dict)


class OutreachDraftResponse(BaseModel):
    candidate_id: int
    job_id: int
    subject: str
    body: str
    outreach_email_id: int | None = None

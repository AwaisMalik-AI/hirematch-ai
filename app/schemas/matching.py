from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MatchResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    job_id: int
    overall_score: float
    semantic_score: float
    skill_match_score: float
    experience_score: float
    education_score: float
    scoring_breakdown: dict[str, Any]
    skill_gaps: list[Any] | dict[str, Any]
    strong_matches: list[Any] | dict[str, Any]
    explanation: str | None
    created_at: datetime


class MatchRunRequest(BaseModel):
    candidate_id: int
    job_id: int
    explain: bool = Field(True, description="Whether to attach LLM explanation")


class BatchMatchResponse(BaseModel):
    job_id: int
    processed: int
    match_ids: list[int]


class ExplainMatchRequest(BaseModel):
    match_result_id: int


class ExplainMatchResponse(BaseModel):
    match_result_id: int
    explanation: str

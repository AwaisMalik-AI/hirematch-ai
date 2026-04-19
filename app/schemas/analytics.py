from typing import Any

from pydantic import BaseModel, Field


class StageCount(BaseModel):
    stage: str
    count: int


class JobPipelineStats(BaseModel):
    job_id: int
    job_title: str
    candidate_counts_by_status: list[StageCount]
    match_count: int
    avg_overall_score: float | None
    screened_count: int


class PipelineOverview(BaseModel):
    total_jobs: int
    active_jobs: int
    total_candidates: int
    jobs: list[JobPipelineStats]


class TopCandidateItem(BaseModel):
    candidate_id: int
    full_name: str | None
    email: str
    overall_score: float
    match_result_id: int


class TopCandidatesResponse(BaseModel):
    job_id: int
    top_n: int
    items: list[TopCandidateItem]

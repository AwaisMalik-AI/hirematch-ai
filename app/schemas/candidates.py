from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.recruitment import CandidateStatus


class CandidateCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(None, max_length=255)
    phone: str | None = Field(None, max_length=64)
    source: str | None = Field(None, max_length=128)
    status: CandidateStatus = CandidateStatus.NEW
    parsed_resume: dict[str, Any] = Field(default_factory=dict)


class CandidateUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    source: str | None = None
    status: CandidateStatus | None = None
    parsed_resume: dict[str, Any] | None = None


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    phone: str | None
    resume_path: str | None
    parsed_resume: dict[str, Any]
    status: CandidateStatus
    source: str | None
    created_at: datetime


class CandidateSearchParams(BaseModel):
    q: str | None = Field(None, description="Search full name or email")
    status: CandidateStatus | None = None
    skill: str | None = Field(None, description="Filter if skill appears in parsed_resume.skills")
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=200)


class ParsedResumeOut(BaseModel):
    skills: list[str] = Field(default_factory=list)
    experience: list[dict[str, Any]] = Field(default_factory=list)
    education: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    summary: str | None = None
    total_years_experience: float | None = None
    current_company: str | None = None
    current_title: str | None = None
    location: str | None = None
    confidence: dict[str, float] = Field(default_factory=dict)


class ResumeUploadResponse(BaseModel):
    candidate_id: int
    resume_path: str
    task_id: str | None = Field(None, description="Celery task id if async parse queued")
    message: str = "Resume stored; parsing scheduled or completed"

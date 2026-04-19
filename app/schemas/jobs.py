from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobCreate(BaseModel):
    title: str = Field(..., max_length=512)
    company: str = Field(..., max_length=255)
    department: str | None = Field(None, max_length=255)
    description: str
    requirements: dict[str, Any] = Field(default_factory=dict)
    preferred: dict[str, Any] = Field(default_factory=dict)
    location: str | None = Field(None, max_length=255)
    seniority_level: str | None = Field(None, max_length=128)
    salary_range: str | None = Field(None, max_length=128)
    employment_type: str | None = Field(None, max_length=64)
    parsed_skills: list[Any] | dict[str, Any] = Field(default_factory=list)
    min_experience_years: float | None = None
    is_active: bool = True


class JobUpdate(BaseModel):
    title: str | None = Field(None, max_length=512)
    company: str | None = Field(None, max_length=255)
    department: str | None = None
    description: str | None = None
    requirements: dict[str, Any] | None = None
    preferred: dict[str, Any] | None = None
    location: str | None = None
    seniority_level: str | None = None
    salary_range: str | None = None
    employment_type: str | None = None
    parsed_skills: list[Any] | dict[str, Any] | None = None
    min_experience_years: float | None = None
    is_active: bool | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    department: str | None
    description: str
    requirements: dict[str, Any]
    preferred: dict[str, Any]
    location: str | None
    seniority_level: str | None
    salary_range: str | None
    employment_type: str | None
    parsed_skills: list[Any] | dict[str, Any]
    min_experience_years: float | None
    is_active: bool
    created_by_id: int | None
    created_at: datetime


class JobParseRequest(BaseModel):
    text: str = Field(..., min_length=20, description="Raw job description text to parse")


class ParsedJDOut(BaseModel):
    requirements: dict[str, Any]
    preferred: dict[str, Any]
    parsed_skills: list[str]
    min_experience_years: float | None
    seniority_level: str | None
    title_suggestion: str | None = None
    confidence: dict[str, float] = Field(default_factory=dict)

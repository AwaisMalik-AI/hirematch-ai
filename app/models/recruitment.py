"""Recruitment domain models."""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CandidateStatus(str, enum.Enum):
    NEW = "new"
    SCREENING = "screening"
    SHORTLISTED = "shortlisted"
    INTERVIEW = "interview"
    OFFERED = "offered"
    HIRED = "hired"
    REJECTED = "rejected"


class ScreeningRecommendation(str, enum.Enum):
    STRONG_YES = "strong_yes"
    YES = "yes"
    MAYBE = "maybe"
    NO = "no"
    STRONG_NO = "strong_no"


class OutreachStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"


class JobDescription(Base):
    __tablename__ = "job_descriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    preferred: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seniority_level: Mapped[str | None] = mapped_column(String(128), nullable=True)
    salary_range: Mapped[str | None] = mapped_column(String(128), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parsed_skills: Mapped[list[Any] | dict[str, Any]] = mapped_column(JSON, default=list, server_default="[]")
    min_experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator = relationship("User", back_populates="job_descriptions")
    match_results = relationship("MatchResult", back_populates="job")
    screening_results = relationship("ScreeningResult", back_populates="job")
    outreach_emails = relationship("OutreachEmail", back_populates="job")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resume_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    parsed_resume: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, name="candidate_status"),
        default=CandidateStatus.NEW,
        server_default=CandidateStatus.NEW.value,
    )
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    match_results = relationship("MatchResult", back_populates="candidate")
    screening_results = relationship("ScreeningResult", back_populates="candidate")
    outreach_emails = relationship("OutreachEmail", back_populates="candidate")


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_match_candidate_job"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_match_score: Mapped[float] = mapped_column(Float, nullable=False)
    experience_score: Mapped[float] = mapped_column(Float, nullable=False)
    education_score: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    skill_gaps: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSON, default=list, server_default="[]")
    strong_matches: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSON, default=list, server_default="[]")
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidate = relationship("Candidate", back_populates="match_results")
    job = relationship("JobDescription", back_populates="match_results")


class ScreeningResult(Base):
    __tablename__ = "screening_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)
    recruiter_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_questions: Mapped[list[Any] | dict[str, Any]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    comparison_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[ScreeningRecommendation | None] = mapped_column(
        Enum(ScreeningRecommendation, name="screening_recommendation"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidate = relationship("Candidate", back_populates="screening_results")
    job = relationship("JobDescription", back_populates="screening_results")


class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), nullable=False, index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job_descriptions.id"), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[OutreachStatus] = mapped_column(
        Enum(OutreachStatus, name="outreach_status"),
        default=OutreachStatus.DRAFT,
        server_default=OutreachStatus.DRAFT.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    candidate = relationship("Candidate", back_populates="outreach_emails")
    job = relationship("JobDescription", back_populates="outreach_emails")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", back_populates="audit_logs")

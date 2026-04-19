"""Resume text extraction + structured parsing (LLM with heuristic fallback)."""

from __future__ import annotations

import io
import logging
import re
from typing import Any

from app.services.llm_client import LLMClient, normalize_skills

logger = logging.getLogger(__name__)


def _extract_pdf_text(file_bytes: bytes) -> str:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []
    for page in doc:
        parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(parts).strip()


def _extract_docx_text(file_bytes: bytes) -> str:
    import docx

    d = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in d.paragraphs if p.text).strip()


def extract_raw_text(file_bytes: bytes, content_type: str | None, filename: str | None = None) -> str:
    ct = (content_type or "").lower()
    name = (filename or "").lower()
    if "pdf" in ct or name.endswith(".pdf"):
        return _extract_pdf_text(file_bytes)
    if "word" in ct or "officedocument" in ct or name.endswith(".docx"):
        return _extract_docx_text(file_bytes)
    if ct.startswith("text/") or name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="replace")
    raise ValueError("Unsupported resume format; use PDF, DOCX, or plain text")


def _heuristic_parse(text: str) -> dict[str, Any]:
    """Lightweight fallback when LLM is unavailable."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blob = " ".join(lines[:400]).lower()
    skill_hits = re.findall(
        r"\b(python|javascript|typescript|java|go|rust|kubernetes|docker|aws|azure|gcp|"
        r"react|vue|angular|node\.?js|sql|postgresql|mongodb|redis|fastapi|django|flask|"
        r"pytorch|tensorflow|mlops|ci/cd|terraform|kafka|spark)\b",
        blob,
        flags=re.I,
    )
    skills = normalize_skills(skill_hits)
    years = re.findall(r"(\d+)\+?\s*years?\s+(?:of\s+)?experience", blob, flags=re.I)
    total_years = float(years[0]) if years else None
    return {
        "skills": skills,
        "experience": [],
        "education": [],
        "certifications": [],
        "projects": [],
        "summary": (lines[0][:500] if lines else None),
        "total_years_experience": total_years,
        "current_company": None,
        "current_title": None,
        "location": None,
        "confidence": {
            "skills": 0.35,
            "experience": 0.2,
            "education": 0.1,
            "overall": 0.25,
        },
    }


class ResumeParser:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm or LLMClient()

    async def parse(
        self,
        file_bytes: bytes,
        content_type: str | None,
        *,
        filename: str | None = None,
    ) -> dict[str, Any]:
        text = extract_raw_text(file_bytes, content_type, filename)
        if not text.strip():
            raise ValueError("Empty resume text after extraction")

        if not self._llm.enabled:
            data = _heuristic_parse(text)
            data["raw_text_preview"] = text[:2000]
            return data

        system = (
            "You extract structured candidate data from resume text. "
            "Return strict JSON with keys: "
            "skills (array of strings), experience (array of objects with title, company, "
            "start_date, end_date, highlights[]), education (array of objects with degree, "
            "institution, year), certifications (strings), projects (objects with name, description), "
            "summary (string), total_years_experience (number or null), current_company, "
            "current_title, location, confidence (object with float 0-1 per major section "
            "plus overall). Normalize skill names to canonical industry forms."
        )
        user = f"Resume text:\n{text[:24000]}"
        try:
            raw = await self._llm.chat_json(system, user, temperature=0.1)
        except Exception as e:
            logger.warning("LLM resume parse failed, using heuristic: %s", e)
            return _heuristic_parse(text)

        skills = normalize_skills(list(raw.get("skills") or []))
        raw["skills"] = skills
        raw.setdefault("experience", [])
        raw.setdefault("education", [])
        raw.setdefault("certifications", [])
        raw.setdefault("projects", [])
        raw.setdefault("confidence", {})
        return raw

# HireMatch AI — private reference (recruiters & interviews)

> Internal notes for talking about the project in interviews. **Do not** commit secrets here; this file is for your own use.

## Elevator pitch (recruiter-friendly)

HireMatch AI is a **recruiting copilot API** that ingests resumes and job descriptions, turns them into structured data, scores candidates against roles with **transparent sub-scores** (not a black box), and helps recruiters with **summaries, screening questions, comparisons, and outreach drafts**. It is built like a real backend service: **PostgreSQL**, **async SQLAlchemy**, **Redis**, **Celery** workers, **JWT auth**, and **environment-based configuration** — no API keys in code.

## What problem it solves

- Parsing unstructured PDFs/DOCX into **consistent JSON** for search and matching.
- Combining **semantic similarity** (embeddings) with **explicit rules** (skills, years, education) so hiring teams can **trust and debug** scores.
- Accelerating phone screens with **gap-aware questions** and **side-by-side** candidate narratives.

## Likely interview questions & concise answers

**Why FastAPI + async SQLAlchemy?**  
Throughput under I/O-bound workloads (DB, HTTP to LLM) improves with async; FastAPI gives typed OpenAPI and validation via Pydantic.

**Why Celery?**  
Resume parsing and batch matching can be slow; offloading them keeps API latency predictable and isolates failures/retries.

**How do you avoid bias / irresponsible AI use?**  
Scores are **explainable** (sub-scores, gaps, stored breakdown). LLM outputs are **assistive** (summary, questions, email draft), not sole decision-makers. Language in prompts asks for neutral, job-relevant content.

**What if the LLM is down?**  
Parsers fall back to **heuristic extraction**; embeddings fall back to a **deterministic offline vector** (documented as non-semantic) so the system still runs for demos and tests.

**How would you productionize auth?**  
Replace open registration with **SSO/OIDC**, shorter-lived access tokens, refresh tokens, password policies, and audit review workflows.

**Database design highlights**  
Unique `(candidate_id, job_id)` on `MatchResult` prevents duplicate rows; enums model pipeline and outreach state; `AuditLog` supports compliance.

**How to test matching?**  
Unit-test pure functions (skill normalization, score math) with fixtures; integration-test API with a test DB; mock LLM/embedding HTTP with `respx` or similar.

## Demo script (2 minutes)

1. Register + login → copy JWT.  
2. `POST /jobs/parse` with a pasted JD → show structured skills/requirements.  
3. `POST /candidates/upload` with a PDF → show `parsed_resume`.  
4. `POST /matching/run` → show `scoring_breakdown`, `skill_gaps`, `strong_matches`.  
5. `POST /screening/questions` → show tailored questions.  

## Things you might improve next

- Alembic migrations + seed scripts  
- Application table linking candidates to jobs explicitly  
- Real SMTP send + webhook tracking for outreach status  
- pgvector for first-class vector search  
- Role-based field masking (PII) in API responses  

---

*Keep this file out of public repos if it contains personal interview notes.*

# HireMatch AI

**Backend-only, production-style API** for an AI recruitment copilot: resume and job-description parsing, **explainable** semantic + rules-based matching, screening assistance, candidate comparison, and outreach drafting. Configuration is **environment-driven** — no secrets in source control.

**Latest:** Hiring crew plus **fairness / bias audit** (`POST /api/v1/fairness/audit`) for proxy-term and skill-coverage checks.

---

## Architecture (high level)

```
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│Resume Upload│────▶│ Resume Parser    │────▶│ Candidate DB │
│ (PDF/DOCX)  │     │ (text + LLM JSON)│     │ parsed_resume│
└─────────────┘     └──────────────────┘     └──────┬───────┘
                                                     │
┌─────────────┐     ┌──────────────────┐              │
│ JD Input    │────▶│ JD Parser        │────▶       │
│ (raw text)  │     │ (LLM structured) │     ┌──────▼───────┐
└─────────────┘     └──────────────────┘     │ Job DB       │
                                               │ requirements │
                                               └──────┬───────┘
                                                      │
                       ┌──────────────────────────────┘
                       ▼
              ┌────────────────────┐
              │ Matching Engine    │
              │ Semantic (embed)   │
              │ + Skills / Exp /   │
              │   Education rules│
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │ MatchResult store  │
              │ scores + gaps +    │
              │ LLM explanation    │
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │ Screening Copilot  │
              │ summary / Qs /     │
              │ compare / outreach │
              └────────────────────┘
```

**Async workers (Celery + Redis)** handle heavy resume parsing and batch matching without blocking the API.

---

## Features by module

| Module | What it does |
|--------|----------------|
| **Auth & RBAC** | JWT bearer auth; roles: `admin`, `recruiter`, `hiring_manager`. |
| **Jobs** | CRUD for `JobDescription`; `POST /jobs/parse` turns raw JD text into structured requirements, preferred skills, seniority, min experience. |
| **Candidates** | CRUD; search by name/email/status/skill substring; **multipart resume upload** with disk storage + optional async parse task. |
| **Matching** | Per pair `(candidate, job)`: semantic similarity (embeddings), weighted skill overlap (required vs preferred), experience vs seniority/min years, education heuristic; persisted `MatchResult` with **skill gaps** and **strong matches**; optional LLM narrative explanation. **Batch match** all non-terminal candidates for a job (sync or Celery). |
| **Screening** | Recruiter-facing summary, tailored screening questions (uses match skill gaps when present), multi-candidate comparison, personalized outreach draft (stored as `OutreachEmail`). |
| **Analytics** | Pipeline overview (per-job counts are for candidates **with a match** to that job), top candidates by `overall_score`. |
| **Audit** | Append-only `AuditLog` for key actions. |

---

## Explainable scoring (example)

Each `MatchResult` stores sub-scores in `[0, 1]` and a JSON **breakdown** (weights, skill lists, experience detail). Example (illustrative):

```json
{
  "overall_score": 0.78,
  "semantic_score": 0.82,
  "skill_match_score": 0.74,
  "experience_score": 0.81,
  "education_score": 0.66,
  "scoring_breakdown": {
    "weights": {
      "semantic": 0.35,
      "skills": 0.35,
      "experience": 0.2,
      "education": 0.1
    },
    "experience_detail": {
      "candidate_years": 6,
      "expected_years": 5,
      "seniority_level": "senior"
    }
  },
  "skill_gaps": ["terraform", "kafka"],
  "strong_matches": ["python", "postgresql", "kubernetes", "aws"]
}
```

Weights are **tunable** via settings (`match_weight_*` in `app/core/config.py` / env).

---

## API endpoints (prefix `/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Register user (portfolio/demo — tighten in production). |
| POST | `/auth/login` | JWT access token. |
| GET/PATCH | `/auth/me` | Current user / update self. |
| GET/POST | `/jobs` | List / create jobs. |
| GET/PATCH/DELETE | `/jobs/{id}` | Job CRUD. |
| POST | `/jobs/parse` | Parse raw JD text → structured fields. |
| GET | `/candidates/search` | Search & filters. |
| POST | `/candidates` | Create candidate. |
| POST | `/candidates/upload` | Upload resume file (+ optional Celery parse). |
| GET/PATCH/DELETE | `/candidates/{id}` | Candidate CRUD. |
| POST | `/matching/run` | Compute / refresh match for one pair. |
| POST | `/matching/batch` | Batch match job (`async_run` queues Celery). |
| GET | `/matching/job/{job_id}` | All matches for a job. |
| GET | `/matching/candidate/{candidate_id}` | All matches for a candidate. |
| POST | `/matching/explain` | LLM explanation for a `MatchResult`. |
| POST | `/screening/summary` | Recruiter summary for `(candidate, job)`. |
| POST | `/screening/questions` | Screening questions. |
| POST | `/screening/compare` | Side-by-side comparison. |
| POST | `/screening/outreach` | Draft outreach email row. |
| GET | `/analytics/pipeline` | Aggregate pipeline stats. |
| GET | `/analytics/jobs/{job_id}/top-candidates` | Top N by score. |
| GET | `/healthz` | Liveness. |

All business routes (except register/login) expect `Authorization: Bearer <token>`.

Interactive docs: `http://localhost:8000/docs` (when running).

---

## Tech stack

- **FastAPI** + **Pydantic v2** + **SQLAlchemy 2 async** + **PostgreSQL** (`asyncpg`)
- **Redis** + **Celery** for background tasks
- **PyMuPDF** + **python-docx** for resume text extraction
- **httpx** for OpenAI-compatible **chat** and **embeddings** (optional `LLM_API_KEY`)
- **Docker Compose** for local full stack

---

## Project structure

```
app/
  main.py                 # FastAPI app
  core/                   # config, database, security, dependencies
  models/                 # User, JobDescription, Candidate, MatchResult, ...
  schemas/                # Request/response DTOs
  services/               # parsers, matching, screening, LLM client
  api/routes/             # HTTP routers
  tasks/                  # Celery app + processing_tasks
tests/
```

---

## Quick start (local)

1. Copy `.env.example` → `.env` and set **`SECRET_KEY`** (≥ 32 chars) and URLs.
2. Create virtualenv, install deps: `pip install -r requirements.txt`
3. Run Postgres & Redis (or use Docker Compose).
4. Bootstrap tables (dev): set `DEBUG=true` so startup runs `init_db()`, **or** run Alembic in production.
5. `uvicorn app.main:app --reload`
6. Celery worker: `celery -A app.tasks.celery_app.celery_app worker --loglevel=INFO`

### Docker Compose

```bash
cp .env.example .env
# Edit .env — set SECRET_KEY and optionally LLM_API_KEY
docker compose up --build
```

API: `http://localhost:8000` · Worker consumes `hirematch.*` tasks.

---

## Scaling notes

- Move from `init_db()` to **Alembic** migrations for production schema evolution.
- Store resume binaries in **object storage** (S3/GCS) instead of a shared volume at scale.
- Cache embeddings per JD version and resume hash in **Redis** to cut LLM cost.
- Split **read replicas** for analytics-heavy queries; keep writes on primary.
- Rate-limit auth and LLM-heavy endpoints; add **idempotency keys** for uploads.
- Harden **`/auth/register`** (invite-only, admin-only, or SSO) for real deployments.

---

## CI/CD

This project includes GitHub Actions for continuous integration:

- **Lint**: Code quality checks with `ruff`
- **Test**: Automated test suite with PostgreSQL and Redis services  
- **Build**: Docker image build verification
- **Deploy**: Configurable deployment to AWS ECS/GCP Cloud Run (see `deploy` job in workflow)

## Observability

- **Structured Logging**: JSON-formatted logs with request tracing
- **Health Checks**: `GET /health` with dependency status (database, Redis, external services)
- **Metrics Ready**: Prometheus-compatible metrics endpoint structure
- **Error Tracking**: Structured error responses with correlation IDs

## Cloud Deployment

Designed for containerized deployment:

- **AWS ECS/Fargate**: Stateless API containers behind ALB
- **AWS RDS**: Managed PostgreSQL with connection pooling
- **AWS ElastiCache**: Managed Redis for Celery broker
- **AWS S3**: Resume and document storage
- **AWS SageMaker**: Optional — deploy matching model as endpoint for high-throughput scoring

---

## License

MIT (or replace with your preferred license for your portfolio).

"""HireMatch AI — FastAPI entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import analytics, auth, candidates, crews, fairness, jobs, matching, screening
from app.core.config import get_settings
from app.core.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.debug:
        import app.models.recruitment  # noqa: F401
        import app.models.user  # noqa: F401

        try:
            await init_db()
            logger.info("Database tables ensured (debug bootstrap)")
        except Exception as e:
            logger.warning("init_db skipped or failed: %s", e)
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI recruitment copilot: resume & JD parsing, explainable matching, screening, outreach, and hiring crews.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

prefix = settings.api_v1_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(jobs.router, prefix=prefix)
app.include_router(candidates.router, prefix=prefix)
app.include_router(matching.router, prefix=prefix)
app.include_router(screening.router, prefix=prefix)
app.include_router(analytics.router, prefix=prefix)
app.include_router(crews.router, prefix=prefix)
app.include_router(fairness.router, prefix=prefix)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": settings.app_name}

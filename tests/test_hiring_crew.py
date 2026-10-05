import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/hirematch")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "x" * 40)

from app.services.hiring_crew import HiringCrew


def test_hiring_crew_heuristic():
    resume = "Senior Python engineer with FastAPI, PostgreSQL, and Celery experience for eight years."
    job = "Looking for a Python FastAPI backend engineer with Celery and PostgreSQL."
    result = HiringCrew().run(resume, job)
    assert result.crew == "hiring"
    assert result.questions
    assert 0 <= result.score <= 1

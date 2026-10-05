from app.services.hiring_crew import HiringCrew
from app.tasks.celery_app import celery_app


@celery_app.task(name="hirematch.run_hiring_crew")
def run_hiring_crew_task(resume_text: str, job_text: str) -> dict:
    result = HiringCrew().run(resume_text, job_text)
    return {
        "crew": result.crew,
        "used_llm": result.used_llm,
        "steps": result.steps,
        "score": result.score,
        "questions": result.questions,
        "summary": result.summary,
    }

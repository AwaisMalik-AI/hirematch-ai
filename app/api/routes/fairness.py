from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser
from app.services.bias_audit import audit

router = APIRouter(prefix="/fairness", tags=["fairness"])


class AuditRequest(BaseModel):
    rationale: str = Field(..., min_length=3)
    required_skills: list[str] = Field(default_factory=list)
    mentioned_skills: list[str] = Field(default_factory=list)


@router.post("/audit")
async def fairness_audit(body: AuditRequest, _: CurrentUser) -> dict:
    return {"kind": "bias_audit", **audit(body.rationale, body.required_skills, body.mentioned_skills)}

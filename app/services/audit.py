"""Append-only audit logging for compliance and debugging."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recruitment import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details or {},
    )
    db.add(row)
    await db.flush()
    return row

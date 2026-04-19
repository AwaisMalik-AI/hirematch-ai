"""Authentication: register, login, current user profile."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import Token, UserCreate, UserLogin, UserRead, UserUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()
    await write_audit(db, user_id=user.id, action="user.register", entity_type="user", entity_id=user.id)
    return user


@router.post("/login", response_model=Token)
async def login(
    body: UserLogin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Authenticate with email and password."""
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")
    token = create_access_token(user.id, extra_claims={"role": user.role.value})
    await write_audit(db, user_id=user.id, action="user.login", entity_type="user", entity_id=user.id)
    return Token(access_token=token)


@router.get("/me", response_model=UserRead)
async def me(current: Annotated[User, Depends(get_current_user)]):
    return current


@router.patch("/me", response_model=UserRead)
async def update_me(
    body: UserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, Depends(get_current_user)],
):
    if body.full_name is not None:
        current.full_name = body.full_name
    if body.role is not None and current.role == UserRole.ADMIN:
        current.role = body.role
    if body.is_active is not None and current.role == UserRole.ADMIN:
        current.is_active = body.is_active
    if body.password:
        current.hashed_password = get_password_hash(body.password)
    await db.flush()
    await write_audit(
        db,
        user_id=current.id,
        action="user.update_self",
        entity_type="user",
        entity_id=current.id,
        details={"fields": body.model_dump(exclude_unset=True)},
    )
    return current

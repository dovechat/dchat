import uuid
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_auth_service, get_current_user, get_db, get_user_service
from schemas.auth_schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenPair,
    UserContext as User,
    UpdateMeRequest,
)
from services.auth_service import AuthService
from services.user_service import  UserService

import logging
log = logging.getLogger("uvicorn.error")

auth_scheme = HTTPBearer()

public_router = APIRouter(tags=["Auth"], prefix="/auth")
private_router = APIRouter(tags=["Auth"], prefix="/auth", dependencies=[Depends(auth_scheme)])

@public_router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Register new user with creating an organization"""
    return await auth_service.register(
        data=data,
        db=db,
    )


@public_router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    refresh_token: str = Body(..., embed=True),
    auth_service: AuthService = Depends(get_auth_service)
):
    return await auth_service.refresh(refresh_token)


@public_router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """OAuth2 compatible token login."""
    log.info('---------- login in new monrepo common auth handler')
    log.info(f'---------- db {db}')

    request = LoginRequest(email=form_data.username, password=form_data.password)

    try:
        tokens = await auth_service.login(request=request, db=db)
        return tokens
    except HTTPException:
        raise
    except Exception as e:
        log.error(f'!!! --- ERROR --- @public_router.post /login e {e}')
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


@private_router.post("/verify")
async def verify(
        code: str,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
        auth_service: AuthService = Depends(get_auth_service)
):
    """Verify code and return specific error status if throttled"""
    result = await auth_service.verify_code(current_user.id, code, db)

    if result == "ok":
        return {"status": "activated"}

    if result == "too_fast":
        raise HTTPException(status_code=429, detail="Too many requests")
    if result == "already_activated":
        return {"status": "already_activated"}  # Use return for 200 OK
    if result == "invalid_code":
        raise HTTPException(status_code=400, detail="Invalid code")
    if result == "user_not_found":
        raise HTTPException(status_code=404, detail="User not found")

    raise HTTPException(status_code=400, detail="Invalid or expired code")


@private_router.post("/switch-tenant")
async def switch_tenant(
    tenant_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
):
    log.info(f'---------- switch_tenant in new monrepo common auth handler tenant_id={tenant_id}')
    return await auth_service.switch_context(db, current_user.id, tenant_id)


@private_router.get("/users/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    user = await user_service.get_me(current_user.id)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "full_name": user.full_name,
        "phone": user.phone,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@private_router.patch("/users/me")
async def update_me(
    data: UpdateMeRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    user = await user_service.update_me(current_user.id, data.full_name, data.phone)
    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "full_name": user.full_name,
        "phone": user.phone,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }

@private_router.post("/users/me/password")
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
):
    await user_service.change_password(current_user.id, data.password, data.password_confirm)
    return {"ok": True}
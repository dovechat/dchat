from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_auth_service, get_db, get_current_user
from schemas.auth_schemas import LoginRequest, RegisterRequest, TokenPair, UserContext as User
from services.auth_service import AuthService


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


@private_router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """OAuth2 compatible token login."""
    request = LoginRequest(email=form_data.username, password=form_data.password)

    try:
        tokens = await auth_service.login(request=request, db=db)
        return tokens
    except HTTPException:
        raise
    except Exception:
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
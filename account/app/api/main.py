"""Main FastAPI application entry point."""

from fastapi import Depends, FastAPI
from fastapi.security import HTTPBearer

from app.api.v1.auth import private_router, public_router
# from app.api.v1.contacts import router as contacts_router
from core.config import settings


app = FastAPI(
    title="DoveChat",
    description="DoveChat admin",
    version="0.1.0",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "persistAuthorization": True
    }
)

app.include_router(public_router, prefix="/api/v1/auth")
app.include_router(private_router, prefix="/api/v1/auth")

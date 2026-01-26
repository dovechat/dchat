"""Main FastAPI application entry point."""
import signal
import uvicorn
from fastapi import Depends, FastAPI
from fastapi.security import HTTPBearer

from app.api.v1.auth import private_router, public_router
from app.api.v1.tenant import tenant_router
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

app.include_router(public_router, prefix="/api/v1")
app.include_router(private_router, prefix="/api/v1")
app.include_router(tenant_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Signal handler for graceful shutdown
def handle_sigterm(_signo, _stack_frame):
    # Add cleanup logic here if needed
    sys.exit(0)

if __name__ == "__main__":
    # Register SIGTERM handler
    signal.signal(signal.SIGTERM, handle_sigterm)
# Run uvicorn programmatically
    uvicorn.run(
        "app.api.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level="info",
        reload=False  # Must be False when running programmatically in prod
    )
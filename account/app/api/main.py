"""Main FastAPI application entry point."""
import signal
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from core.config import settings
from app.api.v1.auth import private_router, public_router
from app.api.v1.lines import line_router
from app.api.v1.tenant import tenant_router
from app.api.v1.channels import channel_router
from app.api.v1.billing import billing_router, tariff_router
from app.api.v1.members import members_router
from app.api.v1.notifications import router as notification_router
from app.api.v1.webhooks import router as webhooks_router

import logging
logging.getLogger('uvicorn.error').setLevel(logging.DEBUG)
log = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="DoveChat",
    description="DoveChat admin",
    version="0.1.0",
    debug=True,
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "persistAuthorization": True
    }
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

'''
[
    "http://0.0.0.0:8071",
    "http://0.0.0.0:8001",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://0.0.0.0:3001",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://194.247.186.84:3001"
],
'''

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.error(f"422 Validation Error: {exc.errors()}")
    log.error(f"Request body: {await request.body()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )


@app.get("/routes")
def list_routes():
    return [route.path for route in app.routes]

app.include_router(public_router, prefix=settings.api_v1_prefix)
app.include_router(private_router, prefix=settings.api_v1_prefix)
app.include_router(tenant_router, prefix=settings.api_v1_prefix)
app.include_router(line_router, prefix=settings.api_v1_prefix)
app.include_router(channel_router, prefix=settings.api_v1_prefix)
app.include_router(billing_router, prefix=settings.api_v1_prefix)
app.include_router(tariff_router, prefix=settings.api_v1_prefix)
app.include_router(notification_router, prefix=settings.api_v1_prefix) 
app.include_router(members_router, prefix=settings.api_v1_prefix)
app.include_router(webhooks_router, prefix=settings.api_v1_prefix)

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
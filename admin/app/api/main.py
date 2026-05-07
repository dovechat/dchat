"""Admin service entry point."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.v1 import users, lines, instances, billing, dashboard, tenants

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("uvicorn.error")

from api.app_start import start

app = start(
    title="DoveChat Admin Service",
    description="Admin WebSocket and REST API for real-time messaging",
    server_prefix="/admin"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # в prod — ограничить до фронта админки
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def h(request, exc):
    logging.error(exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

API_PREFIX = "/api/v1"

app.include_router(dashboard.router, prefix=API_PREFIX)
app.include_router(users.router, prefix=API_PREFIX)
app.include_router(lines.router, prefix=API_PREFIX)
app.include_router(instances.router, prefix=API_PREFIX)
app.include_router(billing.router, prefix=API_PREFIX)
app.include_router(billing.tariff_router, prefix=API_PREFIX)
app.include_router(tenants.router, prefix=API_PREFIX)


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "service": "admin"}
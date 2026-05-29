"""CRM service entrypoint."""
from fastapi import FastAPI
from app.api.v1.webhooks import webhooks_router
from app.api.v1.connections import connections_router
from app.api.v1.install import install_router, static_router
from app.api.v1.outgoing import outgoing_router
from app.api.v1.robots import robots_router

app = FastAPI(title="DoveChat CRM Service")

app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")
app.include_router(install_router, prefix="/api/v1")
app.include_router(outgoing_router, prefix="/api/v1")
app.include_router(robots_router, prefix="/api/v1")
app.include_router(static_router, prefix="")


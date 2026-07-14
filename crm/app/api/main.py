"""CRM service entrypoint."""
from fastapi import FastAPI, Request
from app.api.v1.webhooks import webhooks_router
from app.api.v1.connections import connections_router
from app.api.v1.install import install_router, static_router
from app.api.v1.outgoing import outgoing_router
from app.api.v1.robots import robots_router

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import logging
log = logging.getLogger(__name__)

app = FastAPI(title="DoveChat CRM Service")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://new1782329019.amocrm.ru"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    log.error(f"422 Validation Error: {exc.errors()}")
    log.error(f"Request body: {await request.body()}")
    errors = []
    for e in exc.errors():
        err = dict(e)
        if "ctx" in err and "error" in err["ctx"]:
            err["ctx"] = {"error": str(err["ctx"]["error"])}
        errors.append(err)
    return JSONResponse(
        status_code=422,
        content={"detail": errors}
    )

app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(connections_router, prefix="/api/v1")
app.include_router(install_router, prefix="/api/v1")
app.include_router(outgoing_router, prefix="/api/v1")
app.include_router(robots_router, prefix="/api/v1")
app.include_router(static_router, prefix="")


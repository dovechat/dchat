from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
import logging

log = logging.getLogger(__name__)


def start(title: str, description: str = "", version: str = "0.1.0", server_prefix: str = ""):
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url=None,
        openapi_url="/openapi.json"
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        log.error(f"Unhandled exception: {exc}")
        return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера"})

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

    if server_prefix:
        def custom_openapi():
            if app.openapi_schema:
                return app.openapi_schema
            from fastapi.openapi.utils import get_openapi
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )
            schema["servers"] = [{"url": server_prefix}]
            app.openapi_schema = schema
            return app.openapi_schema
        app.openapi = custom_openapi

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url="./openapi.json",
            title=app.title,
            swagger_ui_parameters=app.swagger_ui_parameters,
        )

    return app
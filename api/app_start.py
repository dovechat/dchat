from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html


def start(title: str, description: str = "", version: str = "0.1.0", server_prefix: str = ""):
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url=None,
        openapi_url="/openapi.json"
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
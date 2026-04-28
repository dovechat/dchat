from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html


def start(title: str, description: str = "", version: str = "0.1.0"):
    app = FastAPI(
        title=title,
        description=description,
        version=version,
        docs_url=None,  # Отключаем стандартный, чтобы не лез в корень
        openapi_url="/openapi.json"
    )

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            # Точка перед путем — это магия, которая делает путь относительным 
            # и заставляет браузер не прыгать в корень домена
            openapi_url="./openapi.json",
            title=app.title,
            # Оставляем дефолтные ссылки, FastAPI сам отдаст их, 
            # если они вшиты, или мы их просто не трогаем
            swagger_ui_parameters=app.swagger_ui_parameters,
        )

    return app
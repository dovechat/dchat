"""Main FastAPI application for Chat service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .v1.chat import router as chat_router
from .v1.websocket import router as websocket_router
from app.consumers.green_whatsapp import GreenWhatsAppListener
from app.consumers.waba import WabaListener
from app.consumers.telegram_listener import TelegramListener
from app.core.kafka_producer import kafka_producer
from contextlib import asynccontextmanager
from core.database import get_db
from api.auth import public_router, private_router
from api.tenant import tenant_router
from api.lines import line_router
from .v1.webhooks import router as webhooks_router

import logging
logging.getLogger("fastapi").setLevel(logging.DEBUG)

app = FastAPI(
    title="DoveChat Chat Service",
    description="WebSocket and REST API for real-time messaging",
    version="0.1.0",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "persistAuthorization": True
    }
)

app.state.green_listener = GreenWhatsAppListener()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3001",
        "http://0.0.0.0:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://194.247.186.84:3001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"422 Validation Error for request {request.method} {request.url}")
    logging.error(f"Request body: {exc.body}")
    logging.error(f"Errors: {exc.errors()}")
    # Возвращаем стандартный ответ, чтобы не ломать клиента
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder({"detail": exc.errors(), "body": exc.body}),
    )




@app.on_event("startup")
async def startup():
    app.state.listener = TelegramListener()
    app.state.green_listener = GreenWhatsAppListener()
    app.state.waba_listener = WabaListener()

app.include_router(public_router, prefix="/api/v1")
app.include_router(private_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(tenant_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")
app.include_router(line_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")

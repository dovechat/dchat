"""Main FastAPI application for Chat service."""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from .v1.chat import router as chat_router
from .v1.websocket import router as websocket_router
from app.consumers.green_whatsapp import GreenWhatsAppListener
from app.consumers.outgoing_consumer import start_consumer
from app.consumers.waba import WabaListener
from app.consumers.telegram_listener import TelegramListener
from app.consumers.vk import VkListener
from app.core.kafka_producer import kafka_producer
from contextlib import asynccontextmanager
from core.database import get_db
from app.core.redis_subscriber import redis_subscriber
from api.auth import public_router, private_router
from api.tenant import tenant_router
from api.lines import line_router
from .v1.webhooks import router as webhooks_router

import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

from api.app_start import start

app = start(
    title="DoveChat Chat Service",
    description="Chat WebSocket and REST API for real-time messaging",
    server_prefix="/api"
)

app.state.green_listener = GreenWhatsAppListener()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
	"https://tg.dove-chat.com:8443",
        "http://chat.127.0.0.1.nip.io",
        "http://127.0.0.1:30087",
        "https://tg.dove-chat.pro",
        "http://localhost",
        "http://127.0.0.1",
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
    log.error(f"422 Validation Error for request {request.method} {request.url}")
    log.error(f"Request body: {exc.body}")
    log.error(f"Errors: {exc.errors()}")
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
    app.state.vk_listener = VkListener()
    asyncio.create_task(redis_subscriber())
    asyncio.create_task(start_consumer(tg_listener=app.state.listener))
    # asyncio.create_task(app.state.listener.start_all())
    asyncio.create_task(app.state.listener._health_check_loop())


@app.on_event("shutdown")
async def shutdown():
    listener = app.state.listener
    for conv_id in list(listener.tasks.keys()):
        client = listener.clients.get(conv_id)
        if client:
            try:
                await client.disconnect()
                log.info(f"Disconnected TG client for {conv_id}")
            except Exception as e:
                log.error(f"Error disconnecting {conv_id}: {e}")
        await listener.stop_listening(conv_id)

prefix = "/v1"
app.include_router(public_router, prefix=prefix)
app.include_router(private_router, prefix=prefix)
app.include_router(chat_router, prefix=prefix)
app.include_router(tenant_router, prefix=prefix)
app.include_router(websocket_router, prefix="/ws")
app.include_router(line_router, prefix=prefix)
app.include_router(webhooks_router, prefix=prefix)


from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


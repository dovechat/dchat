"""Main FastAPI application for Chat service."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .v1.chat import router as chat_router
from .v1.websocket import router as websocket_router
from app.core.kafka_producer import kafka_producer
from contextlib import asynccontextmanager


app = FastAPI(
    title="DoveChat Chat Service",
    description="WebSocket and REST API for real-time messaging",
    version="0.1.0",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": -1,
        "persistAuthorization": True
    }
)

from fastapi.middleware.cors import CORSMiddleware

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

app.include_router(chat_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/ws")
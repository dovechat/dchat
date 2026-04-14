import uuid
from typing import List, Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext
from app.services.bot_service import BotService
from app.services.chat_service import ChatService
from app.services.line_service import LineService
from app.schemas.chat_schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    LineResponse,
    LineWithChannelsResponse,
    MessageResponse,
    MessageCreate,
)
from models.tenants import User

import logging
log = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Chat"])

def get_chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)

def get_bot_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return BotService(db)

def get_line_service(db: AsyncSession = Depends(get_db)) -> LineService:
    return LineService(db)

@router.get("/conversations", response_model=List[ConversationListResponse])
async def list_conversations(
    line_id: str | None = None,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get list of conversations for current tenant"""
    return await chat_service.get_conversations(
        tenant_id=current_user.tenant_id,
        line_id=line_id,
        skip=skip,
        limit=limit
    )

@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Get conversation details and messages"""
    conversation = await chat_service.get_conversation(
        conversation_id=conversation_id,
        tenant_id=current_user.tenant_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get messages for specific conversation"""
    res = await chat_service.get_messages(
        conversation_id=conversation_id,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit
    )
    if len(res) > 0:
        log.info(f"*********** res {res[0]}")
    return res

@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Create new conversation"""
    return await chat_service.create_conversation(
        tenant_id=current_user.tenant_id,
        data=data
    )


@router.post("/messages/tguser", response_model=MessageResponse)
async def create_message_tguser(
    request: Request,
    data: str = Form(...),
    file: UploadFile | None = File(None),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    message_data = MessageCreate.parse_raw(data)
    return await chat_service.create_msg_tguser(
        request=request,
        data=message_data,
        file=file,
        current_user=current_user,
    )

@router.post("/messages/tgbot", response_model=MessageResponse)
async def create_message_tgbot(
    # data: MessageCreate,
    request: Request,
    data: str = Form(...),
    file: UploadFile | None = File(None),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Create new message in conversation"""
    message_data = MessageCreate.parse_raw(data)
    return await chat_service.create_msg_tgbot(
        request=request,
        data=message_data,
        file=file,
        current_user=current_user,
    )

@router.post("/messages/whatsapp/green", response_model=MessageResponse)
async def create_message_whatsapp_green(
    request: Request,
    data: str = Form(...),
    file: UploadFile | None = File(None),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    message_data = MessageCreate.parse_raw(data)
    return await chat_service.create_msg_whatsapp_green(
        data=message_data,
        file=file,
        current_user=current_user,
    )


@router.post("/messages/waba", response_model=MessageResponse)
async def create_message_waba(
    request: Request,
    data: str = Form(...),
    file: UploadFile | None = File(None),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    message_data = MessageCreate.parse_raw(data)
    return await chat_service.create_msg_waba(
        request=request,
        data=message_data,
        file=file,
        current_user=current_user,
    )


@router.post("/bot/webhook/{line_id}")
async def telegram_bot_webhook(
    line_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    from app.services.bot_service import BotService
    bot_service = BotService(db)
    data = await request.json()
    return await bot_service.handle_webhook(line_id, data)


@router.get("/lines", response_model=List[LineResponse])
async def get_my_lines(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    line_service: LineService = Depends(get_line_service)
):
    return await line_service.get_user_lines(
        user_id=current_user.id,
        role=current_user.role,
        tenant_id=current_user.tenant_id
    )


@router.get("/lines/{line_id}/channels", response_model=List[LineResponse])
async def get_line_channels(
    line_id: uuid.UUID,
    current_user: UserContext = Depends(get_current_user),
    line_service: LineService = Depends(get_line_service)
):
    return await line_service.get_line_channels(line_id)


@router.get("/lines-with-channels", response_model=List[LineWithChannelsResponse])
async def get_lines_with_channels(
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    return await chat_service.get_lines_with_available_channels(
        tenant_id=current_user.tenant_id
    )


@router.post("/upload")
async def upload_file(
    request: Request,
    media_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Upload file to S3"""
    log.info(f"Uploading file: {file.filename}")
    result = await chat_service.upload(media_id, file)
    return result
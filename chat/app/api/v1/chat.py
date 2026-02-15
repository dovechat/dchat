import uuid
from typing import List
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext
from app.services.chat_service import ChatService
from app.schemas.chat_schemas import (
    ConversationResponse,
    MessageResponse,
    ConversationListResponse,
    ConversationCreate,
    MessageCreate,
)

router = APIRouter(tags=["Chat"])

def get_chat_service(db: AsyncSession = Depends(get_db)) -> ChatService:
    return ChatService(db)

@router.get("/conversations", response_model=List[ConversationListResponse])
async def list_conversations(
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """Get list of conversations for current tenant"""
    return await chat_service.get_conversations(
        tenant_id=current_user.tenant_id,
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
    return await chat_service.get_messages(
        conversation_id=conversation_id,
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=limit
    )

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


@router.post("/messages", response_model=MessageResponse)
async def create_message(
    data: MessageCreate,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Create new message in conversation"""
    return await chat_service.create_message(
        tenant_id=current_user.tenant_id,
        data=data
    )
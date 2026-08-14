import json
import uuid
from typing import List, Any
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user
from schemas.auth_schemas import UserContext
from app.core.kafka_producer import kafka_producer 
from app.services.bot_service import BotService
from app.services.chat_service import ChatService
from app.services.line_service import LineService
from app.schemas.chat_schemas import (
    ConversationCloseRequest,
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    CrmMessageIn,
    CrmMessageOut,
    LineResponse,
    LineWithChannelsResponse,
    MessageCreate,
    MessageDirection,
    MessageEditRequest,
    MessageResponse,
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


async def _enqueue_outgoing(
    channel_type: str,
    data: MessageCreate,
    files: list[UploadFile],
    current_user: UserContext,
    chat_service: ChatService,
) -> MessageResponse:
    data.media = []
    _, message = await chat_service.conv_msg(data, current_user)
    await kafka_producer.send_message(
        channel_type=channel_type,
        conversation_id=data.conversation_id,
        phone=data.phone,
        crm_message_id=data.crm_message_id,
        text=data.text,
        user_id=current_user.id,
        user_email=current_user.email,
        message_id=message.id,
        files=files,
        template=data.template,
    )
    log.info(f"_enqueue_outgoing crm_message_id={data.crm_message_id} channel_type={channel_type} message_id={message.id}")
    return MessageResponse.model_validate(message)


async def _enqueue_edit(
    message_id: int,
    data: MessageEditRequest,
    current_user: UserContext,
    chat_service: ChatService,
):
    message = await chat_service.msg_repo.get_by_id(message_id)
    if not message or not message.channel_msg_id:
        raise HTTPException(status_code=400, detail="cannot edit")
    conv = await chat_service.conv_repo.get_by_id(message.conversation_id)
    await kafka_producer.send_edit_message(
        channel_type=conv.channel_type,
        conversation_id=message.conversation_id,
        message_id=message.id,
        text=data.text,
        user_id=current_user.id,
        user_email=current_user.email,
        phone=conv.client_phone,
        line_id=str(conv.line_id),
    )
    log.info(f"_enqueue_edit channel_type={conv.channel_type} message_id={message.id}")
    return MessageResponse.model_validate(message)


async def _enqueue_delete(
    message_id: int,
    current_user: UserContext,
    chat_service: ChatService,
):
    log.info(f"\n\n *--**-**-**-- router.delete _enqueue_delete message_id {message_id}")
    message = await chat_service.msg_repo.get_by_id(message_id)
    log.info(f"\n\n *--**-**-**-- router.delete _enqueue_delete message {message}")
    if not message:
        log.error(f"!!! --- ERROR --- !!! Failed kafka_producer.send_delete_message message {message}")
        raise HTTPException(status_code=400, detail="cannot delete")
    conv = await chat_service.conv_repo.get_by_id(message.conversation_id)
    log.info(f"\n\n *--**-**-**-- router.delete _enqueue_delete conv {conv}")
    try:
        await kafka_producer.send_delete_message(
            channel_type=conv.channel_type,
            conversation_id=message.conversation_id,
            message_id=message.id,
            user_id=current_user.id,
            user_email=current_user.email,
            phone=conv.client_phone,
            line_id=str(conv.line_id),
        )
    except Exception as e:
        log.error(f"!!! --- ERROR --- !!! Failed kafka_producer.send_delete_message e {e}")
    log.info(f"_enqueue_delete channel_type={conv.channel_type} message_id={message.id}")
    return {"status": "queued"}


@router.post("/internal/crm-outgoing")
async def crm_outgoing(
    data: str = Form(...),
    channel_type: str = Form(...),
    user_id: uuid.UUID = Form(...),
    user_email: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    chat_service: ChatService = Depends(get_chat_service),
):
    current_user = UserContext(id=user_id, email=user_email, role="user", member="owner")
    log.info(f"\n\n ++++++++++++++ internal/crm-outgoing data {data}  \n\n")
    msg = MessageCreate.model_validate_json(data)
    log.info(f"\n\n ++++++++++++++ internal/crm-outgoing msg {msg}  \n\n")
    return await _enqueue_outgoing(channel_type, msg, files, current_user, chat_service)


@router.post("/internal/crm-delete")
async def crm_delete(
    message_id: int = Form(...),
    channel_type: str = Form(...),
    phone: str = Form(...),
    line_id: uuid.UUID = Form(...),
    user_id: uuid.UUID = Form(...),
    user_email: str = Form(...),
    chat_service: ChatService = Depends(get_chat_service),
):
    current_user = UserContext(id=user_id, email=user_email, role="user", member="owner")
    await chat_service.delete_message(message_id, current_user, phone, line_id, channel_type)


@router.post("/internal/crm-edit")
async def crm_edit(
    message_id: int = Form(...),
    text: str = Form(...),
    channel_type: str = Form(...),
    phone: str = Form(...),
    line_id: uuid.UUID = Form(...),
    user_id: uuid.UUID = Form(...),
    user_email: str = Form(...),
    chat_service: ChatService = Depends(get_chat_service),
):
    current_user = UserContext(id=user_id, email=user_email, role="user", member="owner")
    await chat_service.edit_outgoing_message(message_id, text, current_user, phone, line_id, channel_type)


@router.post("/messages/tgbot", response_model=MessageResponse)
async def create_message_tgbot(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await _enqueue_outgoing("telegram_bot", MessageCreate.parse_raw(data), files, current_user, chat_service)


@router.post("/messages/tguser", response_model=MessageResponse)
async def create_message_tguser(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    log.info(f"\n\n messages tguser  data {data} \n\n")
    data_ = MessageCreate.parse_raw(data)
    log.info(f"\n\n messages tguser  data_ {data_} \n\n")
    return await _enqueue_outgoing("telegram_user", data_, files, current_user, chat_service)


@router.post("/messages/whatsapp/green", response_model=MessageResponse)
async def create_message_whatsapp_green(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await _enqueue_outgoing("whatsapp_green", MessageCreate.parse_raw(data), files, current_user, chat_service)


@router.post("/messages/waba", response_model=MessageResponse)
async def create_message_waba(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await _enqueue_outgoing("waba", MessageCreate.parse_raw(data), files, current_user, chat_service)


@router.post("/messages/waba/template", response_model=MessageResponse)
async def create_message_waba_template(
    conversation_id: uuid.UUID = Form(...),
    template_name: str = Form(...),
    language: str = Form(default="ru"),
    components: str = Form(default="[]"),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    data = MessageCreate(
        conversation_id=conversation_id,
        direction=MessageDirection.outbound,
        text=f"[template:{template_name}]",
        phone="",
        template={"name": template_name, "language": language, "components": json.loads(components)},
    )

    return await _enqueue_outgoing("waba", data, [], current_user, chat_service)
@router.post("/messages/vk", response_model=MessageResponse)
async def create_message_vk(
    data: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await _enqueue_outgoing("vk", MessageCreate.parse_raw(data), files, current_user, chat_service)


@router.patch("/conversations/{conversation_id}/status")
async def set_conversation_status(
    conversation_id: uuid.UUID,
    body: ConversationCloseRequest,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.close_or_open_conversation(
        conversation_id=conversation_id,
        is_closed=body.is_closed,
        user_id=current_user.id,
    )


@router.get("/conversations", response_model=List[ConversationListResponse])
async def list_conversations(
    line_id: uuid.UUID | None = None,
    channel_type: str | None = None,
    is_closed: bool | None = None,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    try:
        return await chat_service.get_conversations_filtered(
            user_id=current_user.id,
            line_id=line_id,
            channel_type=channel_type,
            is_closed=is_closed,
        )
    except Exception as e:
        log.error(f"router.get /conversations failed: {e}", exc_info=True)
        raise


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
    limit: int = Query(20, ge=1, le=1000)
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
    chat_service: ChatService = Depends(get_chat_service),
):
    """Create new conversation"""
    return await chat_service.create_conversation(
        tenant_id=current_user.tenant_id,
        data=data,
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
    log.info(f" \n\n ---------- router.post /bot/webhook/{line_id}  data {data} \n\n ")
    return await bot_service.handle_webhook(line_id, data, request)


from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response
from app.services.status import StatusService
from app.core.dependencies import get_status_service

@router.get("/metrics")
async def metrics(status_service: StatusService = Depends(get_status_service)):
    await status_service.check_all()
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
        user_id=current_user.id
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


@router.post("/internal/crm-message")
async def crm_incoming(
    data: CrmMessageIn,
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.save_crm_incoming(data)


@router.post("/internal/crm-robot-send")
async def crm_robot_send(
    request: Request, 
    data: CrmMessageOut,
    chat_service: ChatService = Depends(get_chat_service),
):
    return await chat_service.robot_send(data)


from app.schemas.chat_schemas import MessageEditRequest

@router.patch("/messages/{message_id}", response_model=MessageResponse)
async def edit_message(
    message_id: int,
    data: MessageEditRequest,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    # return await chat_service.edit_message(message_id, data.text, current_user, tg_listener=request.app.state.listener)
    return await _enqueue_edit(message_id, data, current_user, chat_service)


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    request: Request,
    current_user: UserContext = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    # await chat_service.delete_message(message_id, current_user, tg_listener=request.app.state.listener)
    log.info(f"\n\n *--**-**-**-- router.delete( delete_message {message_id}")
    await _enqueue_delete(message_id, current_user, chat_service)
    return {"ok": True}

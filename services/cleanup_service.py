import uuid
import json
import logging
import httpx
from minio import Minio
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from repo.line_repo import ChannelAccountRepository, InstanceRepository
from core.config import settings
from infra.crypto import decrypt

log = logging.getLogger("uvicorn.error")

GREEN_API_BASE = settings.proxy_green_url


class CleanupService:
    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        channel_account_repo: ChannelAccountRepository,
        instance_repo: InstanceRepository,
    ):
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.channel_account_repo = channel_account_repo
        self.instance_repo = instance_repo
        self.s3 = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )

    async def _cleanup_green_instance(self, line_id: uuid.UUID, channel_account) -> None:
        instance = await self.instance_repo.get_instance_by_line(line_id)
        if not instance or not instance.external_id:
            log.info(f"\n\n ------- no green instance found for line {line_id} ---------- \n\n")
            return

        token = None
        if channel_account and channel_account.credentials_encrypted:
            try:
                creds = json.loads(decrypt(channel_account.credentials_encrypted["encrypted_data"]))
                token = creds["api_token"]
            except Exception as e:
                log.error(f"\n\n ------- green credentials decrypt failed {e} ---------- \n\n")

        if token:
            log.info(f"\n\n ---- +++ ---- Send remove webhook greenapi external_id: {instance.external_id} ---+++---  \n\n")
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    resp = await client.get(f"{GREEN_API_BASE}/waInstance{instance.external_id}/clearMessagesQueue/{token}")
                    log.info(f"\n\n ------- clearMessagesQueue instance={instance.external_id} status={resp.status_code} ---------- \n\n")
                except Exception as e:
                    log.error(f"\n\n ------- clearMessagesQueue failed instance={instance.external_id} {e} ---------- \n\n")

                try:
                    green_set_settiings_url = f"{GREEN_API_BASE}/waInstance{instance.external_id}/setSettings/{token}"
                    resp = await client.post(
                        green_set_settiings_url,
                        json={
                            "webhookUrl": "",
                        }
                    )
                    if not str(resp.status_code).startswith("2"):
                        log.error(f"Send remove webhook returned wrong status code: {resp.status_code} {resp.json()}")
                except httpx.ReadTimeout:
                    msg = f"!!! --- ERROR: Send green remove webhook  {green_set_settiings_url} request returns timeout "
                    log.error(msg)

                try:
                    green_set_settiings_url = f"{GREEN_API_BASE}/waInstance{instance.external_id}/logout/{token}"
                    resp = await client.get(green_set_settiings_url)
                    log.info(f"\n\n ------- logout green_set_settiings_url instance={instance.external_id} status={resp.status_code} {resp.json()} ---------- \n\n")
                except Exception as e:
                    log.error(f"\n\n ------- logout green_set_settiings_url failed instance={instance.external_id} {e} ---------- \n\n")
        else:
            log.info(f"\n\n ------- skipping green API calls: no token for line {line_id} ---------- \n\n")

        await self.instance_repo.update(
            instance,
            allocated_to_line_id=None,
            status="idle",
        )
        log.info(f"\n\n ------- green instance freed: {instance.id} ---------- \n\n")

    async def cleanup_line(self, line_id: uuid.UUID, channel_type: str | None = None) -> dict:
        log.info(f"\n\n ------- cleanup_line started for {line_id} channel_type={channel_type} ---------- \n\n")
        result = {
            "conversations": 0,
            "media_deleted": 0,
            "media_errors": 0,
        }

        channel_account = await self.channel_account_repo.get_by_line_and_type(line_id, channel_type)
        log.info(f"\n\n ------- cleanup_line channel_account: {channel_account} ---------- \n\n")

        conversations = await self.conversation_repo.get_by_line(line_id, channel_type=channel_type)
        log.info(f"\n\n ------- cleanup_line conversations: {len(conversations)} ---------- \n\n")

        for conversation in conversations:
            try:
                media_ids = await self.message_repo.get_media_ids_by_conversation(conversation.id)
                for media_id in media_ids:
                    try:
                        self.s3.remove_object(settings.s3_bucket, media_id)
                        result["media_deleted"] += 1
                        log.info(f"\n\n ------- cleanup_line media deleted: {media_id} ---------- \n\n")
                    except Exception as e:
                        result["media_errors"] += 1
                        log.error(f"\n\n ------- cleanup_line media error: {media_id} {e} ---------- \n\n")
    
                await self.conversation_repo.delete(conversation)
                result["conversations"] += 1
            except Exception as e:
                log.error(f"cleanup_line conversation error: {conversation.id} {e}", exc_info=True)

        if channel_type == "whatsapp_green":
            await self._cleanup_green_instance(line_id, channel_account)

        await self.channel_account_repo.update(
            channel_account,
            session_string=None,
            credentials_encrypted=None,
            bot_token=None,
            connection_status="disconnected",
        )


        log.info(f"\n\n ------- cleanup_line finished: {result} ---------- \n\n")
        return result
"""VK deleted-message sync DAG — polls messages.getHistory per active VK conversation,
diffs against our stored inbound messages, and mirrors deletions to CRM."""
import asyncio
import time
import httpx
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from core.database import AsyncSessionLocal
from infra.crypto import decrypt
from repo.line_repo import ChannelAccountRepository, LineRepository
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from crm.app.services.crm_service import CrmService
from crm.app.core.uow import CrmUnitOfWork
import json
import logging

log = logging.getLogger("airflow.task")

DEFAULT_ARGS = {
    "owner": "dovechat",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
}

RUN_DURATION_SECONDS = 55
CHECK_INTERVAL_SECONDS = 10


async def _get_recent_conversation_message_ids(access_token: str, peer_id: str) -> set[str]:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://api.vk.com/method/messages.getHistory",
            params={
                "peer_id": peer_id,
                "count": 20,
                "v": "5.199",
                "access_token": access_token,
            },
        )
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            log.error(f"vk_delete_sync: messages.getHistory error peer_id={peer_id}: {data['error']}")
            return set()
        return {
            str(message["conversation_message_id"])
            for message in data["response"]["items"]
        }


async def _sync_vk_deletes_once() -> None:
    async with AsyncSessionLocal() as session:
        try:
            channel_repo = ChannelAccountRepository(session)
            line_repo = LineRepository(session)
            conv_repo = ConversationRepository(session)
            msg_repo = MessageRepository(session)

            vk_accounts = await channel_repo.get_multi(filters={"channel_type": "vk"})

            for account in vk_accounts:
                if not account.credentials_encrypted: 
                    continue
                creds = json.loads(decrypt(account.credentials_encrypted["encrypted_data"]))
                access_token = creds.get("access_token")
                line = await line_repo.get_by_id(account.line_id)
                tenant_id = line.tenant_id
                if not access_token:
                    continue

                conversations = await conv_repo.get_multi(
                    filters={"line_id": account.line_id, "channel_type": "vk"}
                )

                for conv in conversations:
                    peer_id = conv.client_phone
                    if not peer_id:
                        continue

                    msgs_from_vk = await _get_recent_conversation_message_ids(access_token, peer_id)

                    messages = await msg_repo.get_multi(
                        filters={"conversation_id": conv.id, "direction": "inbound"},
                        order_by=[("created_at", "desc")],
                        limit=20,
                    )

                    for message in messages:
                        if not message.channel_msg_id:
                            continue
                        if message.channel_msg_id in msgs_from_vk:
                            continue

                        try:
                            crm_uow = CrmUnitOfWork(session)
                            crm_service = CrmService(crm_uow)
                            await crm_service.delete_from_crm(
                                tenant_id=tenant_id,
                                conversation_id=conv.id,
                                client_phone=conv.client_phone,
                                message_id=str(message.id),
                                channel_type="vk",
                            )
                            log.info(
                                f"vk_delete_sync: deleted message.id={message.id} "
                                f"channel_msg_id={message.channel_msg_id} conv={conv.id}"
                            )
                        except Exception as e:
                            log.error(
                                f"vk_delete_sync: delete_from_crm failed message.id={message.id}: {e}"
                            )

            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _run_loop() -> None:
    deadline = time.monotonic() + RUN_DURATION_SECONDS
    while time.monotonic() < deadline:
        await _sync_vk_deletes_once()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


def vk_delete_sync_task(**context):
    log.info("Starting VK delete sync loop")
    asyncio.run(_run_loop())


with DAG(
    dag_id="vk_delete_sync",
    description="Poll VK messages.getHistory and mirror client-side deletions to CRM",
    schedule="* * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["vk", "dovechat"],
) as dag:
    sync_deletes = PythonOperator(
        task_id="vk_delete_sync",
        python_callable=vk_delete_sync_task,
    )
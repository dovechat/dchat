"""Expire DAG — hourly check for channel_accounts past their expires_at."""
import asyncio
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from core.database import AsyncSessionLocal
from repo.line_repo import LineRepository, ChannelAccountRepository, InstanceRepository
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from notification.notification_repo import NotificationSettingsRepository, NotificationLogRepository
from services.line_service import LineService
from notification.notification_service import NotificationService
from services.cleanup_service import CleanupService
from models.tenants import Tenant  # noqa: F401
from models.notifications import NotificationSettings  # noqa: F401
import logging

log = logging.getLogger("airflow.task")

DEFAULT_ARGS = {
    "owner": "dovechat",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
}


async def _expire_channels(now: datetime) -> None:
    async with AsyncSessionLocal() as session:
        try:
            service = LineService(
                line_repo=LineRepository(session),
                channel_account_repo=ChannelAccountRepository(session),
            )
            notification_service = NotificationService(
                settings_repo=NotificationSettingsRepository(session),
                log_repo=NotificationLogRepository(session),
            )
            cleanup_service = CleanupService(
                conversation_repo=ConversationRepository(session),
                message_repo=MessageRepository(session),
                channel_account_repo=ChannelAccountRepository(session),
                instance_repo=InstanceRepository(session),
            )

            results = await service.expire_channels(now)

            for item in results["expired_channels"]:
                channel = item["channel"]
                line = item["line"]

                await notification_service.notify_line_expired(
                    tenant_id=line.tenant_id,
                    line_name=line.name,
                    expires_at=channel.expires_at,
                    channel_type=channel.channel_type.value,
                )

                if item["line_expired"]:
                    for ch in item["all_channels"]:
                        await cleanup_service.cleanup_line(line.id, channel_type=ch.channel_type.value)

            await session.commit()
            log.info(f"Expire results at {now}: {results}")
        except Exception:
            await session.rollback()
            raise


def expire_channels_task(**context):
    execution_date = context["logical_date"]
    log.info(f"Starting expire check at {execution_date}")
    asyncio.run(_expire_channels(execution_date))


with DAG(
    dag_id="channel_expire_check",
    description="Hourly check and expiration of channel_accounts past their expires_at",
    schedule="0 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["lines", "dovechat"],
) as dag:
    expire = PythonOperator(
        task_id="expire_channels",
        python_callable=expire_channels_task,
    )

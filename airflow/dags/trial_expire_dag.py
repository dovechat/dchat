"""Trial Expire DAG — daily cleanup of trial users older than 2 days."""
import asyncio
import httpx
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.lines import LineStatus
from models.notifications import NotificationSettings  # noqa: F401
from models.tenants import Tenant  # noqa: F401
from repo.line_repo import LineRepository, ChannelAccountRepository
from repo.instance_repo import InstanceRepository
from repo.conversation_repo import ConversationRepository
from repo.message_repo import MessageRepository
from repo.user import UserRepository
from repo.membership_repo import MembershipRepository
from notification.notification_repo import NotificationSettingsRepository, NotificationLogRepository
from notification.notification_service import NotificationService
from services.cleanup_service import CleanupService
import logging

log = logging.getLogger("airflow.task")

DEFAULT_ARGS = {
    "owner": "dovechat",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
}


async def _expire_trial_users(now: datetime) -> None:
    cutoff = now - timedelta(days=2)

    async with AsyncSessionLocal() as session:
        try:
            user_repo = UserRepository(session)
            membership_repo = MembershipRepository(session)
            line_repo = LineRepository(session)
            channel_account_repo = ChannelAccountRepository(session)
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

            # Ищем trial-юзеров старше 2 дней
            trial_users = await user_repo.get_multi(
                filters={"status": "trial"},
                limit=10000,
            )
            trial_users = [u for u in trial_users if u.created_at.replace(tzinfo=timezone.utc) < cutoff.replace(tzinfo=timezone.utc)]

            log.info(f"Found {len(trial_users)} trial users older than 2 days")

            total_lines = 0
            total_channels = 0

            for user in trial_users:
                # Берём только тенанты где юзер owner
                memberships = await membership_repo.get_multi(
                    filters={"user_id": user.id, "role": "owner", "is_active": True},
                    limit=1000,
                )

                for membership in memberships:
                    tenant_id = membership.tenant_id

                    # Все линии тенанта
                    lines = await line_repo.get_multi(
                        filters={"tenant_id": tenant_id},
                        limit=10000,
                    )

                    for line in lines:
                        # Все каналы линии
                        channels = await channel_account_repo.get_multi(
                            filters={"line_id": line.id},
                            limit=100,
                        )

                        for channel in channels:
                            try:
                                await line_repo.update(line, status="expired")
                                await cleanup_service.cleanup_line(
                                    line.id,
                                    channel_type=channel.channel_type.value,
                                )
                                total_channels += 1
                                log.info(f"Cleaned channel {channel.id} (line={line.id}, type={channel.channel_type.value})")
                            except Exception as e:
                                log.error(f"cleanup_line failed line={line.id} channel={channel.id}: {e}")

                            if channel.channel_type.value == "telegram_user":
                                try:
                                    async with httpx.AsyncClient() as client:
                                        await client.post(f"http://tg-connector:8000/channels/{line.id}/stop")
                                except Exception as e:
                                    log.error(f"expire_channels: tg-connector stop failed line={line.id}: {e}")

                        # Уведомление об истечении линии
                        try:
                            if channels:
                                ch = channels[0]
                                await notification_service.notify_line_expired(
                                    tenant_id=tenant_id,
                                    line_name=line.name,
                                    expires_at=ch.expires_at,
                                    channel_type=ch.channel_type.value,
                                )
                        except Exception as e:
                            log.error(f"notify_line_expired failed line={line.id}: {e}")

                        total_lines += 1

                await user_repo.update(user, status="inactive")
                log.info(f"User {user.id} marked inactive")

            await session.commit()
            log.info(f"Trial expire done at {now}: users={len(trial_users)}, lines={total_lines}, channels={total_channels}")

        except Exception:
            await session.rollback()
            raise


def expire_trial_users_task(**context):
    execution_date = context["logical_date"]
    log.info(f"Starting trial expire check at {execution_date}")
    asyncio.run(_expire_trial_users(execution_date))


with DAG(
    dag_id="trial_user_expire",
    description="Daily cleanup of trial users and their tenants/lines older than 2 days",
    schedule="0 1 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["trial", "dovechat"],
) as dag:
    expire = PythonOperator(
        task_id="expire_trial_users",
        python_callable=expire_trial_users_task,
    )
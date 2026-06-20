import uuid
import logging
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from repo.line_repo import LineRepository
from notification.notification_repo import NotificationSettingsRepository, NotificationLogRepository
from notification.notification_service import NotificationService

log = logging.getLogger(__name__)
get_session = asynccontextmanager(get_db)

# стало
async def notify_connection_error(line_id: uuid.UUID, channel_type: str | None = None, db: AsyncSession | None = None):
    log.info("notify_connection_error start")
    if db is None:
        async with get_session() as db:
            await _do_notify(db, line_id, channel_type)
    else:
        await _do_notify(db, line_id, channel_type)
    log.info("notify_connection_error end")


async def _do_notify(db: AsyncSession, line_id: uuid.UUID, channel_type: str | None = None):
    line = await LineRepository(db).get_by_id(line_id)
    log.info(f"notify_connection_error line {line}")
    if line:
        notification_service = NotificationService(
            NotificationSettingsRepository(db),
            NotificationLogRepository(db)
        )
        log.info(f"notify_connection_error notification_service {notification_service} tenant_id {line.tenant_id} name {line.name} channel_type {channel_type}")
        await notification_service.notify_line_connection_error(
            tenant_id=line.tenant_id,
            line_name=line.name,
            channel_type=channel_type,
        )
        log.info(f"notify_connection_error notify_line_connection_error ")
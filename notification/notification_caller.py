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
    if db is None:
        async with get_session() as db:
            await _do_notify(db, line_id, channel_type)
    else:
        await _do_notify(db, line_id, channel_type)


async def _do_notify(db: AsyncSession, line_id: uuid.UUID, channel_type: str | None = None):
    line = await LineRepository(db).get_by_id(line_id)
    notification_service = NotificationService(
        NotificationSettingsRepository(db),
        NotificationLogRepository(db)
    )
    await notification_service.notify_line_connection_error(
        tenant_id=line.tenant_id,
        line_name=line.name,
        channel_type=channel_type,
    )
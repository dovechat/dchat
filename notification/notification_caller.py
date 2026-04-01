import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from repo.line_repo import LineRepository
from notification.notification_repo import NotificationSettingsRepository, NotificationLogRepository
from notification.notification_service import NotificationService

log = logging.getLogger(__name__)

async def notify_connection_error(line_id: uuid.UUID, db: AsyncSession = None):
    if db is None:
        async for db_ in get_db():
            db = db_
            break
    await _do_notify(db, line_id)


async def _do_notify(db: AsyncSession, line_id: uuid.UUID):
    line = await LineRepository(db).get_by_id(line_id)
    notification_service = NotificationService(
        NotificationSettingsRepository(db),
        NotificationLogRepository(db)
    )
    await notification_service.notify_line_connection_error(
        tenant_id=line.tenant_id,
        line_name=line.name
    )
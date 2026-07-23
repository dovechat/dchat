from repo.line_repo import ChannelAccountRepository
from core.metrics import provider_status
from app.services.bot_service import BotService

import logging
log = logging.getLogger("uvicorn.error")


class StatusService:
    def __init__(self, db):
        self.db = db
        self.channel_repo = ChannelAccountRepository(db)

    async def check_all(self) -> None:
        accounts = await self.channel_repo.get_one_per_channel_type()
        log.info(f"check_all accounts: {accounts}")
        for acc in accounts:
            log.info(f"acc.channel_type: {acc.channel_type}")
            if acc.channel_type.value == "telegram_bot":
                is_up = await BotService(self.db).check_alive(acc)
                log.info(f"check_all telegram_bot is_up={is_up}")
                provider_status.labels(channel_type="telegram_bot").set(1 if is_up else 0)
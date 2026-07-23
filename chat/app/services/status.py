from repo.line_repo import ChannelAccountRepository
from core.config import settings
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
            elif acc.channel_type.value == "telegram_user":
                is_up = await self.check_platform_alive()
                log.info(f"check_all telegram_user is_up={is_up}")
                provider_status.labels(channel_type="telegram_user").set(1 if is_up else 0)

    async def check_platform_alive(self) -> bool:
        sender = MTProtoSender(
            None,
            retries=1,
            delay=1,
        )

        try:
            await sender.connect(
                ConnectionTcpMTProxyRandomizedIntermediate,
                (
                    settings.tg_proxy_host,
                    int(settings.tg_proxy_port),
                    settings.tg_proxy_secret,
                ),
            )
            return sender.is_connected()

        except Exception as e:
            log.exception(f"Telegram unavailable: {e}")
            return False

        finally:
            await sender.disconnect()



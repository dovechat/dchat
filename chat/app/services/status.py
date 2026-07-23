from repo.line_repo import ChannelAccountRepository
from core.config import settings
from core.metrics import provider_status
from app.services.bot_service import BotService


import logging
log = logging.getLogger("uvicorn.error")


class StatusService:
    def __init__(self, db, telegram_listener=None):
        self.db = db
        self.channel_repo = ChannelAccountRepository(db)
        self.telegram_listener = telegram_listener

    async def check_all(self) -> None:
        accounts = await self.channel_repo.get_one_per_channel_type()
        for acc in accounts:
            if acc.channel_type.value == "telegram_bot":
                is_up = await BotService(self.db).check_alive(acc)
                provider_status.labels(channel_type="telegram_bot").set(1 if is_up else 0)
            elif acc.channel_type.value == "telegram_user":
                is_up = await self._check_telegram_user_alive(acc)
                provider_status.labels(channel_type="telegram_user").set(1 if is_up else 0)

    async def _check_telegram_user_alive(self, acc) -> bool:
        if self.telegram_listener and any(
            c.is_connected() for c in self.telegram_listener.clients.values()
        ):
            return True
        return await self._ping_session(acc)

    async def _ping_session(self, acc) -> bool:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate

        session_string = acc.session_string
        if not session_string:
            return False
        client = TelegramClient(
            StringSession(session_string),
            settings.tg_api_id,
            settings.tg_api_hash,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(settings.tg_proxy_host, int(settings.tg_proxy_port), settings.tg_proxy_secret),
        )
        try:
            await client.connect()
            return await client.is_user_authorized()
        except Exception:
            return False
        finally:
            await client.disconnect()



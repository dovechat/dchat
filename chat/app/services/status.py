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
                is_up = await self.check_platform_alive()
                provider_status.labels(channel_type="telegram_user").set(1 if is_up else 0)

    async def check_platform_alive(self) -> bool:
        import asyncio

        try:
            log.info(
                "Telegram MTProxy healthcheck start host=%s port=%s",
                settings.tg_proxy_host,
                settings.tg_proxy_port,
            )

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    settings.tg_proxy_host,
                    int(settings.tg_proxy_port),
                ),
                timeout=10,
            )

            log.info("Telegram MTProxy TCP connection established")

            writer.close()
            await writer.wait_closed()

            log.info("Telegram MTProxy healthcheck success")
            return True

        except Exception:
            log.exception("Telegram MTProxy healthcheck failed")
            return False





















    async def _check_telegram_user_alive____(self, acc) -> bool:
        has_live = bool(
            self.telegram_listener
            and any(c.is_connected() for c in self.telegram_listener.clients.values())
        )
        log.info(f"telegram_user check: acc.id={acc.id} has_live_client={has_live}")
        if has_live:
            return True
        return await self._ping_session(acc)

    async def _ping_session(self, acc) -> bool:
        import traceback
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate

        session_string = acc.session_string
        log.info(f"session_string {session_string}")
        log.info(f"telegram_user ping: acc.id={acc.id} session_string_present={bool(session_string)} len={len(session_string) if session_string else 0}")
        if not session_string:
            log.warning(f"telegram_user ping: no session_string for acc.id={acc.id}")
            return False

        try:
            string_session = StringSession(session_string)
            log.info(f"telegram_user ping: acc.id={acc.id} StringSession parsed ok")
        except Exception as e:
            log.error(f"telegram_user ping: acc.id={acc.id} StringSession parse failed: {e}\n{traceback.format_exc()}")
            return False

        client = TelegramClient(
            string_session,
            settings.tg_api_id,
            settings.tg_api_hash,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=(settings.tg_proxy_host, int(settings.tg_proxy_port), settings.tg_proxy_secret),
        )
        try:
            await client.connect()
            log.info(f"telegram_user ping: acc.id={acc.id} connect ok, is_connected={client.is_connected()}")
            authorized = await client.is_user_authorized()
            log.info(f"telegram_user ping: acc.id={acc.id} is_user_authorized={authorized}")
            return authorized
        except Exception as e:
            log.error(f"telegram_user ping: acc.id={acc.id} connect/auth failed: {e}\n{traceback.format_exc()}")
            return False
        finally:
            try:
                await client.disconnect()
                log.info(f"telegram_user ping: acc.id={acc.id} disconnect ok")
            except Exception as e:
                log.error(f"telegram_user ping: acc.id={acc.id} disconnect failed: {e}")



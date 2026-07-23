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
                is_up = await self._check_telegram_user_alive()
                provider_status.labels(channel_type="telegram_user").set(1 if is_up else 0)










    async def _check_telegram_user_alive(self) -> bool:
        import logging
        from collections import defaultdict

        from telethon.network.connection.tcpmtproxy import (
            ConnectionTcpMTProxyRandomizedIntermediate,
        )
        from telethon.network.mtprotosender import MTProtoSender

        sender = None

        try:
            loggers = defaultdict(lambda: logging.getLogger("telethon"))

            secret = settings.tg_proxy_secret.strip()

            log.info(f"\n\n Telegram MTProto healthcheck connect secret {secret} \n\n")

            if len(secret) == 66 and secret[:2] in ("dd", "ee"):
                secret = secret[2:]

            sender = MTProtoSender(
                auth_key=None,
                loggers=loggers,
            )

            log.info(f"\n\n Telegram MTProto healthcheck connect sender {sender} \n\n")

            connection = ConnectionTcpMTProxyRandomizedIntermediate(
                settings.tg_proxy_host,
                int(settings.tg_proxy_port),
                2,
                proxy=(
                    settings.tg_proxy_host,
                    int(settings.tg_proxy_port),
                    secret,
                ),
                loggers=loggers,
            )

            log.info(f"\n\n Telegram MTProto healthcheck connect connection {connection} \n\n")

            import asyncio

            await asyncio.wait_for(
                sender.connect(connection),
                timeout=10,
            )
            log.info(f"\n\n Telegram MTProto healthcheck connect sender.is_connected() {sender.is_connected()} \n\n")
            return sender.is_connected()

        except Exception:
            log.exception("Telegram MTProto healthcheck failed")
            return False

        finally:
            if sender:
                try:
                    await sender.disconnect()
                except Exception:
                    pass





















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



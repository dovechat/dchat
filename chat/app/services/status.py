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

    async def check_all(self) -> None:
        accounts = await self.channel_repo.get_one_per_channel_type()
        for acc in accounts:
            if acc.channel_type.value == "telegram_bot":
                is_up = await BotService(self.db).check_alive(acc)
                provider_status.labels(channel_type="telegram_bot").set(1 if is_up else 0)
            elif acc.channel_type.value == "telegram_user":
                is_up = await self.check_platform_alive()
                provider_status.labels(channel_type="telegram_user").set(1 if is_up else 0)
            elif acc.channel_type.value == "whatsapp_green":
                is_up = await self._check_url("https://api.green-api.com")
                provider_status.labels(channel_type="whatsapp_green").set(1 if is_up else 0)
            elif acc.channel_type.value == "waba":
                is_up = await self._check_url("https://waba-v2.360dialog.io/")
                provider_status.labels(channel_type="waba").set(1 if is_up else 0)
            elif acc.channel_type.value == "vk":
                is_up = await self._check_url("https://api.vk.com/method/utils.getServerTime?v=5.199")
                provider_status.labels(channel_type="vk").set(1 if is_up else 0)

    async def _check_url(self, url: str) -> bool:
        import httpx
        log.info(f"connection {url} start")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url)
                log.info(f"connection {url} established statis  {resp.status_code}")
                res = resp.status_code < 500
                log.info(f"connection res {res}")
                return res
        except Exception:
            log.exception(f"provider check failed url={url}")
            return False



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




from functools import wraps

def prometheus_metrics(channel_type: str, event_type: str = "message"):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                with webhook_processing_seconds.labels(channel_type=channel_type, event_type=event_type).time():
                    result = await func(*args, **kwargs)
                webhook_errors_total.labels(channel_type=channel_type, status="success").inc()
                return result
            except Exception:
                webhook_errors_total.labels(channel_type=channel_type, status="error").inc()
                raise
        return wrapper
    return decorator
















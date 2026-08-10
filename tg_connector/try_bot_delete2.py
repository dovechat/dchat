import asyncio
import logging
import sys

from telethon import events

from tg_client import TelegramClientWrapper
from core.config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

log = logging.getLogger("tg_delete_test")


async def main():
    log.info("=== Telegram Bot MTProto delete PoC ===")

    client = TelegramClientWrapper()

    # Создаём MTProto-соединение через твой прокси
    await client.connect()
    log.info("Connected to Telegram")

    # Авторизуем именно BOT через MTProto
    await client.client.sign_in(
        bot_token="7899850117:AAG8YhcGRIDBrFO2oSj7YRSCvx2mNxi5zh8",
    )

    me = await client.get_entity("me")

    log.warning(
        "MTProto AUTH: id=%s username=%s bot=%s",
        me.id,
        me.username,
        getattr(me, "bot", None),
    )

    log.info("Bot authorized via MTProto")

    me = await client.get_entity("me")

    log.info(
        "Logged in: id=%s username=%s",
        me.id,
        me.username,
    )

    @client.on(events.MessageDeleted)
    async def deleted(event):
        log.warning("!!! MESSAGE DELETED !!!")
        log.warning("deleted_ids=%s", event.deleted_ids)
        log.warning("raw=%s", event.original_update)

    log.info("Listening for message deletions...")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        log.info("Ctrl-C received")
    finally:
        await client.disconnect()
        log.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
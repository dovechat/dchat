import asyncio
import logging
import sys
from pathlib import Path

from telethon import TelegramClient, events
from core.config import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

log = logging.getLogger("tg_delete_test")

API_ID = settings.tg_api_id
API_HASH = settings.tg_api_hash

SESSION = Path("/mono/tg_connector/telegram_delete_test.session")

client = TelegramClient(
    str(SESSION),
    API_ID,
    API_HASH,
)


@client.on(events.MessageDeleted)
async def deleted(event):
    log.warning("!!! MESSAGE DELETED !!!")
    log.warning("deleted_ids=%s", event.deleted_ids)
    log.warning("raw=%s", event.original_update)


async def main():
    log.info("Starting Telegram MTProto test")
    log.info("Session: %s", SESSION)

    if SESSION.exists():
        log.info("Session exists, connecting...")
    else:
        log.info("Session does not exist, creating new session...")

    await client.start()

    me = await client.get_me()

    log.info(
        "Logged in: id=%s username=%s phone=%s",
        me.id,
        me.username,
        me.phone,
    )

    log.info("Listening for deletions...")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
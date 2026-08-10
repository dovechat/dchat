import asyncio
import logging
from telethon import TelegramClient, events
from core.config import settings

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s", stream=sys.stdout)
log = logging.getLogger("uvicorn")

API_ID = settings.tg_api_id
API_HASH = settings.tg_api_hash

# Сессия сохранится в telegram_user.session
client = TelegramClient("telegram_user", API_ID, API_HASH)


@client.on(events.MessageDeleted)
async def deleted(event):
    log.info(f"DELETED: {event.deleted_ids}")
    log.info(f"RAW {event.original_update}:")


async def main():
    log.info("START tg_bot_delete ")
    await client.start()
    log.info("after await client.start()")

    me = await client.get_me()
    log.info(f"Logged in: {me.id} @{me.username}")

    # Просто показываем диалоги, чтобы найти бота
    async for dialog in client.iter_dialogs():
        if dialog.is_user:
            log.info(dialog.id, dialog.name, dialog.entity.username)

    log.info("Listening for deletions...")
    await client.run_until_disconnected()


asyncio.run(main())
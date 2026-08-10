import asyncio
from telethon import TelegramClient, events
from core.config import settings

API_ID = settings.tg_api_id
API_HASH = settings.tg_api_hash

# Сессия сохранится в telegram_user.session
client = TelegramClient("telegram_user", API_ID, API_HASH)


@client.on(events.MessageDeleted)
async def deleted(event):
    print("DELETED:", event.deleted_ids)
    print("RAW:", event.original_update)


async def main():
    await client.start()

    me = await client.get_me()
    print(f"Logged in: {me.id} @{me.username}")

    # Просто показываем диалоги, чтобы найти бота
    async for dialog in client.iter_dialogs():
        if dialog.is_user:
            print(dialog.id, dialog.name, dialog.entity.username)

    print("Listening for deletions...")
    await client.run_until_disconnected()


asyncio.run(main())
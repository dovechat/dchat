import asyncio
import logging
import sys

from telethon import events

from tg_client import TelegramClientWrapper


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

log = logging.getLogger("tg_delete_test")


async def main():
    log.info("=== Telegram delete PoC ===")

    client = TelegramClientWrapper()

    # Создаём НОВОЕ MTProto-соединение через твой прокси
    await client.connect()
    log.info("Connected to Telegram")

    # Авторизация новой session
    if not await client.is_user_authorized():
        phone = input("Telegram phone: ").strip()

        result = await client.start_phone(phone)

        phone_code_hash = result.phone_code_hash

        code = input("Telegram code: ").strip()

        session_string = await client.check_code(
            code=code,
            phone=phone,
            phone_code_hash=phone_code_hash,
        )

        log.info("NEW SESSION CREATED")
        log.info("session_string=%s", session_string)

    else:
        log.info("Session is already authorized")

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

    @client.on(events.NewMessage)
    async def new_message(event):
        log.warning(
            "NEW MESSAGE: chat_id=%s sender_id=%s text=%r",
            event.chat_id,
            event.sender_id,
            event.raw_text,
        )


    log.info("Listening for message deletions...")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        log.info("Ctrl-C received")
    finally:
        log.info("Logging out test session...")
        await client.client.log_out()
        await client.disconnect()
        log.info("Test session logged out")


if __name__ == "__main__":
    asyncio.run(main())
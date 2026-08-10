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
    log.info("=== Telegram Bot MTProto delete PoC ===")

    client = TelegramClientWrapper()

    await client.connect()
    log.info("Connected to Telegram")

    await client.client.sign_in(
        bot_token="7899850117:AAG8YhcGRIDBrFO2oSj7YRSCvx2mNxi5zh8",
    )

    me = await client.client.get_me()

    log.warning(
        "MTProto AUTH: id=%s username=%s bot=%s",
        me.id,
        me.username,
        me.bot,
    )

    @client.on(events.NewMessage)
    async def new_message(event):
        log.warning(
            "!!! NEW MESSAGE !!! chat_id=%s sender_id=%s text=%r",
            event.chat_id,
            event.sender_id,
            event.raw_text,
        )

    @client.on(events.MessageDeleted)
    async def deleted(event):
        log.warning("!!! MESSAGE DELETED !!!")
        log.warning("deleted_ids=%s", event.deleted_ids)
        log.warning("raw=%s", event.original_update)

    log.info("Listening for messages and deletions...")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        log.info("Ctrl-C received")
    finally:
        await client.disconnect()
        log.info("Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
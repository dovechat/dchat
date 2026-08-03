import httpx
import logging
import sys
from io import BytesIO
from infra.utils import get_file_from_s3

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s", stream=sys.stdout)
log = logging.getLogger("uvicorn")


async def send_message(client, entity, text, media):
    log.info(f"\n\n send_telegram_message entity {entity} text {text} media {media} \n\n ")

    if media:
        files = []
        for item in media:
            content, filename = await get_file_from_s3(item["id"])
            file = BytesIO(content)
            file.name = item.get("file_name", filename)
            file.mime_type = item.get("mime_type")
            files.append(file)

        return await client.send_file(
            entity,
            files,
            caption=text or "",
        )

    return await client.send_message(
        entity,
        text or "",
    )
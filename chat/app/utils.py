import httpx
import json
from core.config import settings
from infra.crypto import decrypt

import logging
log = logging.getLogger("uvicorn.error")

async def get_file_from_s3(media_id: str) -> tuple[bytes, str]:
    from services.storage_service import StorageService
    url = StorageService().presigned_url(media_id)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        cd = response.headers.get('content-disposition', '')
        filename = 'unnamed'
        if 'filename=' in cd:
            filename = cd.split('filename=')[-1].strip('"\'')
        log.info(f"utils.get_file_from_s3 url {url}")
        return response.content, filename

def decrypt_credentials(encrypted: dict) -> dict:
    """
    Decrypt credentials for internal use
    # !!! Placeholder - implement actual decryption
    """
    # TODO: Use cryptography library
    if "encrypted_data" in encrypted:
        log.info(f"************* _decrypt_credentials encrypted {encrypted} {type(encrypted['encrypted_data'])}")
        creds_js = decrypt(encrypted["encrypted_data"])
        creds = json.loads(creds_js)
        return creds
    return {}
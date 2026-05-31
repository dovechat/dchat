import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from core.config import settings
from core.database import AsyncSessionLocal
from crm.app.repositories.crm_repo import CrmConnectionRepository
from crm.app.services.providers.bitrix.client import BitrixClient
from infra.crypto import decrypt


async def main(domain: str):
    async with AsyncSessionLocal() as session:
        repo = CrmConnectionRepository(session)
        rows = await repo.get_multi(filters={"domain": domain}, limit=1)
        if not rows:
            print(f"Connection not found for domain={domain}")
            return
        conn = rows[0]
        access_token = decrypt(conn.access_token_enc)
        bx = BitrixClient(domain=domain, access_token=access_token)
        for connector_id, connector_name in zip(
            settings.BITRIX_CONNECTOR_MAP.values(),
            settings.BITRIX_CONNECTOR_NAMES.values(),
        ):
            try:
                await bx.register_connector(connector_id, name=connector_name)
                print(f"registered: {connector_id}")
            except Exception as e:
                print(f"failed {connector_id}: {e}")
        try:
            line_id = await bx.create_open_line("DoveChat")
            print(f"open line created: {line_id}")
        except Exception as e:
            print(f"create_open_line failed: {e}")


if __name__ == "__main__":
    domain = sys.argv[1] if len(sys.argv) > 1 else "b24-3oom3u.bitrix24.ru"
    asyncio.run(main(domain))
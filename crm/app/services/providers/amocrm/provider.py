"""amoCRM provider — stub."""
from crm.app.services.providers.base import CrmProvider


class AmoCrmProvider(CrmProvider):
    async def send_message(self, **kwargs) -> dict:
        raise NotImplementedError("amoCRM not implemented yet")

    async def handle_webhook(self, data: dict) -> dict:
        raise NotImplementedError("amoCRM not implemented yet")

    async def refresh_tokens(self) -> dict:
        raise NotImplementedError("amoCRM not implemented yet")

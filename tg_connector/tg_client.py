import logging

import aiohttp
from telethon import TelegramClient
from telethon.network.connection.tcpmtproxy import ConnectionTcpMTProxyRandomizedIntermediate
from telethon.sessions import StringSession

from core.config import settings

log = logging.getLogger("uvicorn.error")


class TelegramClientWrapper:
    def __init__(self, use_mock=False, session_string: str | None = None):
        self.use_mock = use_mock
        self.session_string = session_string

        self.client: TelegramClient | None = None
        self.phone: str | None = None
        self.phone_code_hash: str | None = None

        self.api_id = int(settings.tg_api_id)
        self.api_hash = settings.tg_api_hash

        self.mock_url = "http://telegram-mock:8082"

        self.proxy = (
            settings.tg_proxy_host,
            int(settings.tg_proxy_port),
            settings.tg_proxy_secret,
        )

    async def __call__(self, request):
        return await self.client(request)

    async def connect(self):
        if self.session_string:
            session = StringSession(self.session_string)
        else:
            session = StringSession()

        self.client = TelegramClient(
            session,
            self.api_id,
            self.api_hash,
            connection=ConnectionTcpMTProxyRandomizedIntermediate,
            proxy=self.proxy,
            auto_reconnect=True,
            connection_retries=5,
            retry_delay=1,
            timeout=5,
        )

        await self.client.connect()

    async def disconnect(self):
        if self.client:
            await self.client.disconnect()
            self.client = None

    async def start_qr(self):
        await self.connect()
        qr_login = await self.client.qr_login()
        return qr_login

    async def start_phone(self, phone: str):
        self.phone = phone

        if self.use_mock:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mock_url}/send_code",
                    json={"phone": phone}
                ) as resp:
                    data = await resp.json()
                    self.phone_code_hash = data["phone_code_hash"]
                    return {"phone_code_hash": self.phone_code_hash}
        else:
            await self.connect()

            if not await self.client.is_user_authorized():
                result = await self.client.send_code_request(phone)
                self.phone_code_hash = result.phone_code_hash
                return result

    async def check_code(self, code: str, phone: str, phone_code_hash: str):
        if self.use_mock:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.mock_url}/check_code",
                    json={"code": code, "phone": phone, "phone_code_hash": phone_code_hash}
                ) as resp:
                    data = await resp.json()
                    return data["session"]
        else:
            if not self.client or not self.phone:
                raise RuntimeError("Call start_phone first")

            await self.client.sign_in(
                phone=self.phone,
                code=code,
                phone_code_hash=self.phone_code_hash
            )
            return self.client.session.save()

    def on(self, event):
        return self.client.on(event)

    async def is_user_authorized(self):
        return await self.client.is_user_authorized()
        
    def is_connected(self):
        return self.client and self.client.is_connected()
        
    async def run_until_disconnected(self):
        await self.client.run_until_disconnected()
    
    async def get_entity(self, *args, **kwargs):
        return await self.client.get_entity(*args, **kwargs)
    
    async def send_file(self, *args, **kwargs):
        return await self.client.send_file(*args, **kwargs)
    
    async def send_message(self, *args, **kwargs):
        return await self.client.send_message(*args, **kwargs)

    async def edit_message(self, *args, **kwargs):
        return await self.client.edit_message(*args, **kwargs)
    
    async def delete_messages(self, *args, **kwargs):
        return await self.client.delete_messages(*args, **kwargs)




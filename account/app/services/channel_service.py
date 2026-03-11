import httpx
import uuid
import json
from typing import Optional
from fastapi import HTTPException
from app.repositories.line_repo import (
    ChannelAccountRepository,
    InstanceRepository,
    LineRepository,
)
from app.schemas.channel_schemas import (
    TelegramBotCredentials,
    TelegramUserCredentials,
    VKCredentials,
    ChannelAccountResponse,
)
from app.schemas.line_schemas import ChannelType 
from core.config import settings
from infra.crypto import decrypt, encrypt
from models.lines import ChannelAccount, Line

import logging

log = logging.getLogger("uvicorn.error")


class ChannelAccountService:
    """Service for managing channel accounts and credentials"""

    def __init__(
            self,
            channel_repo: ChannelAccountRepository,
            line_repo: LineRepository,
            instance_repo: InstanceRepository
    ):
        self.channel_repo = channel_repo
        self.line_repo = line_repo
        self.instance_repo = instance_repo

    def _encrypt_credentials(self, credentials: dict) -> dict:
        """
        Encrypt credentials before storing
        # !!! Placeholder - implement actual encryption
        """
        # TODO: Use cryptography library (Fernet, etc.)
        creds_js = json.dumps(credentials)
        encrypted = encrypt(creds_js)  # Temporary placeholder
        return {"encrypted_data": encrypted}

    def _decrypt_credentials(self, encrypted: dict) -> dict:
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

    async def _verify_line_channel_type(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            expected_type: str
    ) -> None:
        """Verify line exists and has correct channel type"""
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        if line.channel_type != expected_type:
            raise HTTPException(
                status_code=400,
                detail=f"Line channel type is {line.channel_type}, expected {expected_type}"
            )

    async def get_account(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID
    ) -> ChannelAccountResponse:
        """Get channel account info (without decrypted credentials)"""
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        account = await self.channel_repo.get_by_line(line_id)

        if not account:
            return ChannelAccountResponse(
                id = None,
                line_id = line.id,
                channel_type=line.channel_type,
            )
            # raise HTTPException(status_code=404, detail="Channel account not found")
        print("----------------- account.credentials_encrypted", account.credentials_encrypted)
        credentials = self._decrypt_credentials(account.credentials_encrypted)
        if credentials is not None:
            log.info(f"\n\n *************** credentials {type(credentials)} {credentials} \n\n ")
        phone = credentials.get("phone") if credentials else None
        log.info(f"\n\n *************** phone {phone}\n\n ")


        return ChannelAccountResponse(
            id=account.id,
            line_id=account.line_id,
            channel_type=line.channel_type,
            phone=phone,
            state_json=account.state_json,
            updated_at=account.updated_at.isoformat() if account.updated_at else None
        )

    async def set_webhook(self, line_id, bot_token):
        try:
            # raise Exception("Test retry")
            log.info(f"\n\n +++++++++++++  data {settings.tg_webhook_url}/{line_id}  \n\n")
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/setWebhook",
                    json={
                        "url": f"{settings.tg_webhook_url}/{line_id}"
                    },
                )
                log.info(f"res {res.json()}")
            log.info(f"\n\n +++++++++++++ set_webhook with httpx.AsyncClient done \n\n")
        except Exception as e:
            log.error(f"Send set_webhook failed : {e}")

    async def update_telegram_bot(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            credentials: TelegramBotCredentials
    ) -> ChannelAccountResponse:
        """Update Telegram Bot credentials"""
        await self._verify_line_channel_type(line_id, tenant_id, "telegram_bot")

        log.info(f"\n\n ------------ credentials {credentials} \n\n")

        encrypted = self._encrypt_credentials(credentials.model_dump())

        account = await self.channel_repo.get_by_line(line_id)
        if account:
            updated = await self.channel_repo.update_account(
                account,
                credentials_encrypted=encrypted
            )
        else:
            # Create if doesn't exist
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                credentials_encrypted=encrypted
            )

        # send webhook on telegram
        log.info(f"\n\n ------------ send webhook on telegram \n\n")
        await self.set_webhook(line_id, credentials.bot_token)

        line = await self.line_repo.get_line_by_id(line_id, tenant_id)

        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=line.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def update_telegram_user(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            credentials: TelegramUserCredentials
    ) -> ChannelAccountResponse:
        """Update Telegram User credentials"""
        # await self._verify_line_channel_type(line_id, tenant_id, "telegram_user")
        log.info(f"\n\n !!!!!! ******************* channel_service update_telegram_user credentials {credentials} \n\n")
        phone = credentials.phone
        session_string = credentials.session_string
        encrypted = self._encrypt_credentials(credentials.model_dump())
        log.info(f"\n\n !!!!!! ******************* encrypted {encrypted} \n\n")
        account = await self.channel_repo.get_by_line(line_id)
        if account:
            account.session_string = credentials.session_string
            log.info(f"\n\n ******************* account {account} \n\n")
            log.info(f"\n\n ******************* account.session_string {account.session_string} \n\n")
            updated = await self.channel_repo.update_account(
                account,
                credentials_encrypted=encrypted,
                phone=phone,
                session_string=session_string,
            )
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                credentials_encrypted=encrypted,
                phone=phone,
                session_string=session_string,
            )

        line = await self.line_repo.get_line_by_id(line_id, tenant_id)

        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=line.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def update_whatsapp_green(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            id_instance: str,
            api_token: str
    ) -> ChannelAccountResponse:
        """Update WhatsApp Green API credentials"""
        # 1. Проверяем линию и получаем её
        log.info("+++++++++++ update_whatsapp_green ++++++++++++")
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        log.info(f"+++++++++++ line {line} ++++++++++++")
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")
        log.info(f"line.channel_type {line.channel_type} ChannelType.WHATSAPP_GREEN {ChannelType.WHATSAPP_GREEN}")
        if line.channel_type.value != ChannelType.WHATSAPP_GREEN.value:
            raise HTTPException(
                status_code=400,
                detail=f"Line channel type is {line.channel_type}, expected whatsapp_green"
            )
        log.info(f"+++++++++++ line AFTER {line} ++++++++++++")
        # 2. Шифруем токен (id_instance не шифруем, это public)
        credentials = {
            "id_instance": id_instance,
            "api_token": api_token
        }
        encrypted = self._encrypt_credentials(credentials)

        # 3. Сохраняем в channel_accounts
        account = await self.channel_repo.get_by_line(line_id)
        if account:
            updated = await self.channel_repo.update_account(
                account,
                credentials_encrypted=encrypted
            )
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                credentials_encrypted=encrypted
            )

        # после сохранения account, но до return:

        # 4. Обновляем external_id в instances
        # если есть доступ к сессии
        await self.instance_repo.update_by_line(
            line_id=line_id,
            external_id=str(id_instance)  # id_instance и так строка
        )

        # 4. Возвращаем ответ
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=line.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def get_qr_from_green(self, id_instance: str, api_token: str) -> str:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.green-api.com/waInstance{id_instance}/qr/{api_token}"
            )
            response.raise_for_status()
            data = response.json()
            log.info(f"----------------- data {data} ")
            if data.get("type") == "qrCode":
                return data["message"]  # base64
            raise HTTPException(400, "Failed to get QR")

    async def update_vk(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            credentials: VKCredentials
    ) -> ChannelAccountResponse:
        """Update VK credentials"""
        await self._verify_line_channel_type(line_id, tenant_id, "vk")

        encrypted = self._encrypt_credentials(credentials.model_dump())

        account = await self.channel_repo.get_by_line(line_id)
        if account:
            updated = await self.channel_repo.update_account(
                account,
                credentials_encrypted=encrypted
            )
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                credentials_encrypted=encrypted
            )

        line = await self.line_repo.get_line_by_id(line_id, tenant_id)


        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=line.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )




    '''
    Needs to move to connector service, it's shouldn't belong to account service 
    async def update_state(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            state_json: dict
    ) -> ChannelAccountResponse:
        """Update only state_json (e.g., connection status)"""
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")

        account = await self.channel_repo.get_by_line(line_id)
        if not account:
            raise HTTPException(status_code=404, detail="Channel account not found")

        updated = await self.channel_repo.update_account(
            account,
            state_json=state_json
        )

        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=line.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )
    '''
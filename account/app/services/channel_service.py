import httpx
import uuid
import json
from typing import Optional
from fastapi import HTTPException
from app.repositories.line_repo import LineRepository
from repo.instance_repo import InstanceRepository
from repo.line_repo import ChannelAccountRepository
from app.schemas.channel_schemas import (
    TelegramBotCredentials,
    TelegramUserCredentials,
    VKCredentials,
    ChannelAccountResponse,
)
from schemas.line_schemas import ChannelType 
from services.cleanup_service import CleanupService
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
        if encrypted and "encrypted_data" in encrypted:
            log.info(f"************* _decrypt_credentials encrypted {encrypted} {type(encrypted['encrypted_data'])}")
            creds_js = decrypt(encrypted["encrypted_data"])
            creds = json.loads(creds_js)
            return creds
        return {}

    async def _verify_line_exists(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
    ) -> Line:
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            raise HTTPException(status_code=404, detail="Line not found")
        return line

    async def get_account(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            channel_type: ChannelType
    ) -> ChannelAccountResponse:
        line = await self._verify_line_exists(line_id, tenant_id)
        account = await self.channel_repo.get_by_line_and_type(line_id, channel_type)
        if not account:
            return ChannelAccountResponse(
                id=None,
                line_id=line.id,
                channel_type=channel_type,
            )
        credentials = self._decrypt_credentials(account.credentials_encrypted)
        phone = credentials.get("phone") if credentials else None
        
        log.info(f"\n\n -- ChannelService.get_account account {account.__dict__} -- \n\n")
        
        return ChannelAccountResponse(
            id=account.id,
            line_id=account.line_id,
            channel_type=account.channel_type,
            phone=phone,
            state_json=account.state_json,
            updated_at=account.updated_at.isoformat() if account.updated_at else None
        )

    async def get_accounts(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
    ) -> list[ChannelAccountResponse]:
        await self._verify_line_exists(line_id, tenant_id)
        accounts = await self.channel_repo.get_by_line(line_id)
        result = []
        for account in accounts:
            
            credentials = self._decrypt_credentials(account.credentials_encrypted)
            phone = credentials.get("phone") if credentials else None
            cha_resp = ChannelAccountResponse(
                id=account.id,
                line_id=account.line_id,
                channel_type=account.channel_type,
                phone=phone,
                state_json=account.state_json,
                updated_at=account.updated_at.isoformat() if account.updated_at else None,
                expires_at=account.expires_at.isoformat() if account.expires_at else None,
                connection_status=account.connection_status,  # добавить
            )
            log.info(f"\n\n --------- ChannelAccountService.get_accounts cha_resp {cha_resp} \n\n")
            result.append(cha_resp)
        res = sorted(result, key=lambda x: x.channel_type)
        return res

    async def update_account(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            channel_type: ChannelType,
    ) -> ChannelAccountResponse:
        log.info(f"\n\n --- ChannelAccountService.update_account line_id {line_id}  channel_type {channel_type} --- \n\n")
        account = await self.channel_repo.get_by_line_and_type(line_id, channel_type)
        if not account:
            raise HTTPException(status_code=404, detail="Channel not found")

        new_status = "connected" if account.connection_status.value != "connected" else "disconnected"
        log.info(f"\n\n --- account.connection_status {account.connection_status} new_status {new_status} --- \n\n")
        await self.channel_repo.update_account(account, connection_status=new_status)
        account = await self.channel_repo.get_by_line_and_type(line_id, channel_type)
        return ChannelAccountResponse.model_validate(account)


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
        await self._verify_line_exists(line_id, tenant_id)
        encrypted = self._encrypt_credentials(credentials.model_dump())
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.TELEGRAM_BOT)
        if account:
            updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.TELEGRAM_BOT,
                credentials_encrypted=encrypted
            )
        await self.set_webhook(line_id, credentials.bot_token)
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def update_telegram_user(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            credentials: TelegramUserCredentials
    ) -> ChannelAccountResponse:
        await self._verify_line_exists(line_id, tenant_id)
        phone = credentials.phone
        session_string = credentials.session_string
        encrypted = self._encrypt_credentials(credentials.model_dump())
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.TELEGRAM_USER)
        if account:
            updated = await self.channel_repo.update_account(
                account,
                credentials_encrypted=encrypted,
                phone=phone,
                session_string=session_string,
            )
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.TELEGRAM_USER,
                credentials_encrypted=encrypted,
                phone=phone,
                session_string=session_string,
            )
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    '''
    async def update_whatsapp_green(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            id_instance: str,
            api_token: str
    ) -> ChannelAccountResponse:
        await self._verify_line_exists(line_id, tenant_id)
        credentials = {"id_instance": id_instance, "api_token": api_token}
        encrypted = self._encrypt_credentials(credentials)
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.WHATSAPP_GREEN)
        if account:
            updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.WHATSAPP_GREEN,
                credentials_encrypted=encrypted
            )
        await self.instance_repo.update_by_line(line_id=line_id, external_id=str(id_instance))
        await self._set_green_webhook(line_id, id_instance, api_token)
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )
        '''

    async def update_whatsapp_green(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            id_instance: str | None = None,
            api_token: str | None = None
    ) -> ChannelAccountResponse:
        log.info(
            f"=== update_whatsapp_green START: line={line_id}, tenant={tenant_id}, id_instance={id_instance}, api_token={'***' if api_token else None}")

        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        log.info(f"Line from DB: {line.id if line else None}")
        if not line:
            raise HTTPException(404, "Line not found")

        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.WHATSAPP_GREEN)
        log.info(
            f"Account from DB: {account.id if account else None}, state_json={account.state_json if account else None}")

        if not account:
            log.info("Account not found, creating new...")
            account = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.WHATSAPP_GREEN,
                credentials_encrypted={}
            )
            log.info(f"Account created: {account.id}")

        # Если креды не переданы, пытаемся взять из pending
        if not id_instance or not api_token:
            log.info("No credentials in request, checking pending...")
            pending_id = account.state_json.get("pending_instance_id") if account.state_json else None
            log.info(f"Pending instance id: {pending_id}")
            if not pending_id:
                log.error("No pending instance, raising 400")
                raise HTTPException(400, "No pending instance. Please connect instance first.")
            instance = await self.instance_repo.get_by_id(pending_id)
            log.info(
                f"Instance: {instance.id if instance else None}, provider={instance.provider if instance else None}, external_id={instance.external_id if instance else None}")
            if not instance or instance.provider.value != "green":
                raise HTTPException(400, "Invalid instance")
            id_instance = instance.external_id
            api_token = instance.token
            instance.status =  "busy"
            instance.allocated_to_line_id = line_id
            await self.instance_repo.update(instance)
            log.info(f"Using instance credentials: id_instance={id_instance}, token={'***' if api_token else None}")
            # Очищаем pending
            await self.channel_repo.update_account(account, state_json={})
            log.info("Cleared pending from state_json")

        token = decrypt(instance.token)

        # Сохраняем credentials
        credentials = {"id_instance": id_instance, "api_token": token}
        encrypted = self._encrypt_credentials(credentials)
        log.info("Credentials encrypted")

        updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        log.info(f"Account updated: {updated.id}")

        # Привязываем инстанс, если он был взят из pending
        if 'instance' in locals() and instance and not instance.allocated_to_line_id:
            await self.instance_repo.allocate_instance(instance, line_id)
            log.info(f"Instance {instance.id} allocated to line {line_id}")

        # Устанавливаем вебхук
        await self._set_green_webhook(line_id, id_instance, token)
        log.info("Webhook set")

        log.info("=== update_whatsapp_green END")
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def connect_whatsapp_green(self, line_id: uuid.UUID, tenant_id: uuid.UUID) -> dict:
        log.info(f"******** channel_service connect_whatsapp_green line_id {line_id} tenant_id {tenant_id}")
        # 1. Проверяем линию
        line = await self.line_repo.get_line_by_id(line_id, tenant_id)
        if not line:
            log.error(f"!!! --- ERROR --- channel_service connect_whatsapp_green line {line} NOT FOUND")
            raise HTTPException(404, "Line not found")

        log.info(f"******** channel_service connect_whatsapp_green line {line}")

        '''
        # 2. Проверяем, нет ли уже аккаунта WhatsApp Green для этой линии
        existing_account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.WHATSAPP_GREEN)
        log.info(f"******** channel_service connect_whatsapp_green existing_account {existing_account} line_id {line_id}")
        if existing_account:
            raise HTTPException(400, "WhatsApp Green account already exists for this line")
        '''
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.WHATSAPP_GREEN)
        # 3. Берём свободный инстанс
        log.info(f"******** channel_service connect_whatsapp_green account {account}")
        instance = await self.instance_repo.get_free_green_instance()
        log.info(f"******** channel_service connect_whatsapp_green instance {instance}")
        if not instance:
            log.error(f"!!! --- ERROR --- channel_service connect_whatsapp_green line {line} No free WhatsApp Green instance available")
            raise HTTPException(404, "No free WhatsApp Green instance available")

        state = {}
        state["pending_instance_id"] = str(instance.id)
        await self.channel_repo.update_account(account, state_json=state)

        '''
        if instance.external_id == "7103547230" and not instance.token:
            token = encrypt("8a531316aee0453e8b68a4975f32b5f59919fc4a177e4e919a")
            instance.token = token
            log.debug(f"channel_service connect_whatsapp_green token {token}")
            await self.instance_repo.update(instance)
        '''

        if instance.token is not None:
            token = decrypt(instance.token)
        else:
            log.error(f"!!! --- ERROR --- channel_service connect_whatsapp_green line {line} Instance token is None")
            raise HTTPException(404, "Set up your instance token")
            

        log.info(f"*+*+*+*+* channel_service connect_whatsapp_green instance {instance}")

        # 4. Получаем QR от Green API
        qr = await self.get_qr_from_green(instance.external_id, token)

        log.info(f"******** channel_service connect_whatsapp_green qr {qr}")

        # 5. Сохраняем временные данные (например, в state_json линии)
        await self.line_repo.update(line, state_json={"pending_instance_id": str(instance.id), "qr": qr})

        log.info(f"******** channel_service connect_whatsapp_green return qr")

        return {"qr": qr}


    async def _set_green_webhook(self, line_id, id_instance, api_token):
        green_wh_url = f"https://api.green-api.com/waInstance{id_instance}/setSettings/{api_token}"
        our_wh_url = f"{settings.host_url}/api/v1/webhooks/whatsapp/green/{line_id}"
        log.info(f"our_wh_url {our_wh_url}")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    green_wh_url,
                    json={
                        "webhookUrl": our_wh_url,
                        "outgoingWebhook": "yes",
                        "stateWebhook": "yes",
                        "incomingWebhook": "yes"
                    }
                )
            if not str(res.status_code).startswith("2"):
                log.error(f"Send green set_webhook returned wrong status code: {res.status_code}")
            else:
                log.info(f"Webhook set our_wh_url {our_wh_url}")
        except httpx.ReadTimeout:
            msg = f"!!! --- ERROR: Send green set_webhook  {green_wh_url} request returns timeout "
            log.error(msg)
            raise HTTPException(status_code=504, detail=msg)
        except Exception as e:
            msg = f"!!! --- ERROR: Send green set_webhook failed : {e}"
            log.error(msg)
            status = res.status_code if 'res' in dir() else 500
            raise HTTPException(status_code=status, detail=msg)

    async def get_qr_from_green(self, id_instance: str, api_token: str) -> str:
        log.info(f"----------------- id_instance {id_instance} api_token {api_token} ")
        green_wh_url =  f"https://api.green-api.com/waInstance{id_instance}/qr/{api_token}"
        async with httpx.AsyncClient() as client:
            try:
                    res = await client.get(
                        green_wh_url
                    )
                    res.raise_for_status()
                    data = res.json()
                    log.info(f"----------------- data {data} ")
                    if data.get("type") == "qrCode":
                        return data["message"]  # base64
                    raise HTTPException(400, "Failed to get QR")
            except httpx.ReadTimeout:
                log.error(f"!!! --- ERROR: Send green QR request timeout  {green_wh_url} request returns timeout ")
            except Exception as e:
                log.error(f"!!! --- ERROR: Send green QR request {e} status_code {res.status_code} {res.json()}")

    async def update_waba(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            api_key: str
    ) -> ChannelAccountResponse:
        await self._verify_line_exists(line_id, tenant_id)
        credentials = {"api_key": api_key}
        encrypted = self._encrypt_credentials(credentials)
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.WABA)
        if account:
            updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.WABA,
                credentials_encrypted=encrypted
            )
        await self._set_waba_webhook(line_id, api_key)
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def _set_waba_webhook(self, line_id, api_key):
        log.info(f"\n\n line_id {line_id} api_key {api_key} \n\n")
        data = {
                        "url": f"{settings.host_url}/api/v1/webhooks/whatsapp/waba/{line_id}"
                    }
        log.info(f"\n\n data {data} \n\n")
        waba_wh_url = "https://waba-sandbox.360dialog.io/v1/configs/webhook"
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    waba_wh_url,
                    headers = {
                        "D360-API-KEY": api_key,
                        "Content-Type": "application/json"
                    },
                    json = data
                )
            if not str(res.status_code).startswith("2"):
                log.error(f"Send WABA set_webhook returned wrong status code: {res.status_code}")
        except httpx.ReadTimeout:
            log.error(f"!!! --- ERROR: Send WABA set_webhook  {waba_wh_url} request returns timeout ")
        except Exception as e:
            log.error(f"Send green set_webhook failed : {e}")

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


    async def line_cleanup(self, line_id: uuid.UUID, tenant_id: uuid.UUID):
        accounts = await self.get_accounts(line_id, tenant_id)
        for account in accounts:
            await cleanup_service.cleanup_line(line_id, channel_type=account.channel_type)
        return {"status": "ok"}



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
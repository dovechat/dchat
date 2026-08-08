import httpx
import uuid
import json
import secrets
from typing import Optional
from fastapi import HTTPException
from app.repositories.line_repo import LineRepository
from repo.crm_repo import CrmSettingsRepository
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

PHKEYS = {
    "telegram_user": "phone",
    "telegram_bot": "group_id",
    "vk": "group_id",
    'whatsapp_green':"phone",
    "waba": "",
}

class ChannelAccountService:
    """Service for managing channel accounts and credentials"""

    def __init__(
            self,
            channel_repo: ChannelAccountRepository,
            line_repo: LineRepository,
            instance_repo: InstanceRepository,
            crm_line_repo: CrmSettingsRepository,
    ):
        self.channel_repo = channel_repo
        self.line_repo = line_repo
        self.instance_repo = instance_repo
        self.crm_line_repo = crm_line_repo

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
            # log.info(f"************* _decrypt_credentials encrypted {encrypted} {type(encrypted['encrypted_data'])}")
            creds_js = decrypt(encrypted["encrypted_data"])
            creds = json.loads(creds_js)
            log.info(f"************* _decrypt_credentials encrypted creds {creds} ")
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
            phkey = PHKEYS[account.channel_type.value]
            # phone = credentials.get("phone") if credentials and "phone" in credentials.keys()  else account.phone
            phone = credentials.get(phkey) if  credentials and  phkey in credentials.keys()  else account.phone
            log.info(f"\n\n --++--  channes_service get_accounts  account {account} ch_type {account.channel_type}  phone {phone}  credentials {credentials} phone {phone}\n\n")
            amo_link = await self.crm_line_repo.get_by_line_and_channel(
                account.line_id, account.channel_type.value
            )
            cha_resp = ChannelAccountResponse(
                id=account.id,
                line_id=account.line_id,
                channel_type=account.channel_type,
                phone=phone,
                state_json=account.state_json,
                updated_at=account.updated_at.isoformat() if account.updated_at else None,
                expires_at=account.expires_at.isoformat() if account.expires_at else None,
                connection_status=account.connection_status,
                amo_connected=amo_link is not None,
            )
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


    async def set_webhook(self, line_id, bot_token, secret_token):
        try:
            # raise Exception("Test retry")
            wh_url = f"{settings.tg_webhook_domain}/api/v1/bot/webhook/{line_id}"
            log.info(f"\n\n +++++++++++++  wh_url {wh_url}  \n\n")
            
            async with httpx.AsyncClient(trust_env=False) as client:
                res = await client.post(
                    f"{settings.tg_bot_send_url}/bot{bot_token}/setWebhook",
                    json={
                        "url": wh_url,
                        "secret_token": secret_token
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

        token = secrets.token_urlsafe(32)
        credentials.secret_token = token

        log.debug(f"\n\n ******* credentials {credentials} \n\n")
        phone = credentials.bot_token.split(":")[0]

        encrypted = self._encrypt_credentials(credentials.model_dump())
        account = await self.channel_repo.get_by_line_and_type(line_id, ChannelType.TELEGRAM_BOT)
        if account:
            updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        else:
            updated = await self.channel_repo.create_account(
                line_id=line_id,
                channel_type=ChannelType.TELEGRAM_BOT,
                credentials_encrypted=encrypted,
                phone=phone
            )
        await self.channel_repo.update_account(account, connection_status="connected", phone=phone)
        await self.set_webhook(line_id, credentials.bot_token, token)
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
        log.info(f"\n\n --------- credentials {credentials.__dict__}\n\n")
        if not credentials.phone.startswith("+"):
            credentials.phone = "+" + credentials.phone
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

        instance = None

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

        token = decrypt(instance.token)  if instance else api_token

        if id_instance and api_token:
            await self._set_green_webhook(line_id, id_instance, token)
            log.info("Webhook set")

        phone = None
        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                resp = await client.get(f"https://api.green-api.com/waInstance{id_instance}/getWaSettings/{token}")
                settings = resp.json()
                phone_raw = settings.get("phone")
                if phone_raw:
                    phone = "+" + phone_raw
                    break
                log.info(f"Green phone not ready yet, attempt {attempt + 1}")
                await asyncio.sleep(2)
        log.info(f"Green phone resolved: {phone}")

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
        if instance:
            log.info(f"******** channel_service connect_whatsapp_green instance {instance} {instance.__dict__} ")
        if not instance:
            log.error(f"!!! --- ERROR --- channel_service connect_whatsapp_green line {line} No free WhatsApp Green instance available")
            raise HTTPException(404, "No free WhatsApp Green instance available")

        state = {}
        state["pending_instance_id"] = str(instance.id)
        await self.channel_repo.update_account(account, state_json=state, connection_status='disconnected')

        if instance.token is not None:
            token = decrypt(instance.token)
        else:
            log.error(f"!!! --- ERROR --- channel_service connect_whatsapp_green line {line} Instance token is None")
            raise HTTPException(400, "Set up your instance token")
            

        log.info(f"*+*+*+*+* channel_service connect_whatsapp_green instance {instance}")

        # 4. Получаем QR от Green API
        qr = await self.get_qr_from_green(instance.external_id, token)

        log.info(f"******** channel_service connect_whatsapp_green qr {qr}")

        # 5. Сохраняем временные данные (например, в state_json линии)
        await self.line_repo.update(line, state_json={"pending_instance_id": str(instance.id), "qr": qr})

        log.info(f"******** channel_service connect_whatsapp_green return qr")

        return {"qr": qr, "id_instance": instance.external_id, "api_token": token}


    async def _set_green_webhook(self, line_id, id_instance, api_token):
        green_wh_url = f"{settings.proxy_green_url}/waInstance{id_instance}/setSettings/{api_token}"
        our_wh_url = f"{settings.proxy_green_wh}/api/v1/webhooks/whatsapp/green/{line_id}"
        log.info(f"our_wh_url {our_wh_url}")
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    green_wh_url,
                    json={
                        "webhookUrl": our_wh_url,
                        "webhookUrlToken": settings.green_api_token,
                        "outgoingWebhook": "yes",
                        "stateWebhook": "yes",
                        "incomingWebhook": "yes",
                        "editedMessageWebhook": "yes",
                        "deletedMessageWebhook": "yes"
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
            msg = f"!!! --- ERROR: Send green set_webhook failed : {e} "
            log.error(msg)
            raise HTTPException(status_code=400, detail=msg)

    async def get_qr_from_green(self, id_instance: str, api_token: str) -> str:
        log.info(f"get_qr_from_green id_instance={id_instance}")
        url = f"{settings.proxy_green_url}/waInstance{id_instance}/qr/{api_token}"
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(url, timeout=30)
            except httpx.ReadTimeout:
                raise HTTPException(408, detail="Таймаут подключения к WhatsApp")
            res.raise_for_status()
            data = res.json()
            log.info(f"get_qr_from_green response {data}")
            if data.get("type") == "qrCode":
                return data["message"]  # base64
            msg = data.get("message", "Failed to get QR")
            log.error(f"get_qr_from_green error {data}")
            raise HTTPException(400, detail=msg)

    async def update_waba(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            api_key: str
    ) -> ChannelAccountResponse:
        await self._verify_line_exists(line_id, tenant_id)

        token = secrets.token_hex(32)
        credentials = {"api_key": api_key, "token": token}
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
        await self._set_waba_webhook(line_id, api_key, token)
        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
            state_json=updated.state_json,
            updated_at=updated.updated_at.isoformat() if updated.updated_at else None
        )

    async def _set_waba_webhook(self, line_id, api_key, token: str):
        log.info(f"\n\n line_id {line_id} api_key {api_key} \n\n")
        data = {
                        "url": f"{settings.host_url}/api/v1/webhooks/whatsapp/waba/{line_id}/{token}"
                    }
        log.info(f"\n\n data {data} \n\n")
        waba_wh_url = f"https://waba-sandbox.360dialog.io/v1/configs/webhook"
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

    async def _vk_verify_token(self, client: httpx.AsyncClient, access_token: str) -> None:
        resp = await client.get(
            "https://api.vk.com/method/groups.getById",
            params={"access_token": access_token, "v": "5.199"}
        )
        result = resp.json()
        if result.get("error"):
            raise ValueError(f"VK token error: {result['error']['error_msg']}")

    async def _vk_add_callback_server(
        self,
        client: httpx.AsyncClient,
        group_id: str,
        access_token: str,
        secret_key: str,
        line_id: uuid.UUID
    ) -> int:
        wh_url = f"{settings.vk_webhook_domain}/api/v1/webhooks/vk/{line_id}"
        log.info(f"wh_url {wh_url}")
        resp = await client.post(
            "https://api.vk.com/method/groups.addCallbackServer",
            data={
                "group_id": group_id,
                "title": "dchat",
                "url": wh_url,
                "secret_key": secret_key or "",
                "access_token": access_token,
                "v": "5.199"
            }
        )
        log.info(f"_vk_add_callback_server resp {resp}")
        result = resp.json()
        log.info(f"_vk_add_callback_server result {result}")
        if result.get("error"):
            raise ValueError(f"VK callback error: {result['error']['error_msg']}")
        return result["response"]["server_id"]

    async def _vk_set_callback_settings(
            self,
            client: httpx.AsyncClient,
            group_id: str,
            server_id: int,
            access_token: str
    ) -> None:
        resp = await client.post(
            "https://api.vk.com/method/groups.setCallbackSettings",
            data={
                "group_id": group_id,
                "server_id": server_id,
                "message_new": 1,
                "message_reply": 1,
                "message_edit": 1,
                "access_token": access_token,
                "v": "5.199"
            }
        )
        result = resp.json()
        if result.get("error"):
            raise ValueError(f"VK settings error: {result['error']['error_msg']}")

    async def update_vk(
            self,
            line_id: uuid.UUID,
            tenant_id: uuid.UUID,
            credentials: VKCredentials
    ) -> ChannelAccountResponse:
        await self._verify_line_exists(line_id, tenant_id,)
        creds_dict = credentials.model_dump()
        log.info("ChannelAccountService update_vk")
        async with httpx.AsyncClient() as client:
            await self._vk_verify_token(client, credentials.access_token)
            log.info("ChannelAccountService update_vk after _vk_verify_token ")
            server_id = await self._vk_add_callback_server(
                client, credentials.group_id, credentials.access_token, credentials.secret_key or "", line_id
            )
            log.info(f"VK server_id: {server_id}, group_id: {credentials.group_id}")
            creds_dict["server_id"] = server_id
            await self._vk_set_callback_settings(client, credentials.group_id, server_id, credentials.access_token)

        encrypted = self._encrypt_credentials(creds_dict)
        account = await self.channel_repo.get_by_line_and_type(line_id, "vk")

        if account:
            updated = await self.channel_repo.update_account(account, credentials_encrypted=encrypted)
        else:
            updated = await self.channel_repo.create_account(line_id=line_id, credentials_encrypted=encrypted)

        line = await self.line_repo.get_line_by_id(line_id, tenant_id)

        return ChannelAccountResponse(
            id=updated.id,
            line_id=updated.line_id,
            channel_type=updated.channel_type,
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
"""CRM service — routes to the right provider."""
import httpx
import json
import jwt
import  time
import uuid
import logging
from fastapi import HTTPException
from core.config import settings
from infra.crypto import decrypt
from models.crm import CrmAccount
from models.messages import MessageDirection
from schemas.chat_schemas import MessageCreate, MessageStatus
from crm.app.schemas.crm_schemas import AmoLineConnectRequest
from crm.app.services.providers.bitrix.provider import BitrixProvider
from crm.app.services.providers.amocrm.provider import AmoCrmClient, AmoCrmProvider

log = logging.getLogger("uvicorn.error")

PROVIDERS = {
    "bitrix24": BitrixProvider,
    "amocrm": AmoCrmProvider,
}

def get_provider(conn: CrmAccount):
    cls = PROVIDERS.get(conn.crm_type)
    if not cls:
        raise ValueError(f"Unknown CRM type: {conn.crm_type}")
    return cls(conn)


class CrmService:
    def __init__(self, uow):
        self._uow = uow

    async def send_to_crm(
            self,
            tenant_id: uuid.UUID,
            conversation_id: uuid.UUID,
            client_phone: str,
            client_name: str,
            text: str,
            message_id: str,
            channel_type: str,
            media: list[dict] = [],
    ) -> str | None:
        log.info(f"start send_to_crm tenant_id {tenant_id} channel_type {channel_type}")
        conn = await self._uow.crm_accounts.get_by_tenant_and_channel(tenant_id, channel_type)
        log.info(f"send_to_crm conn {conn}")
        if not conn:
            return

        log.info(f"send_to_crm conn2 {conn}")
        provider = get_provider(conn)
        conversation = await self._uow.conversations.get_by_id(conversation_id)
        crm_chat_id = conversation.crm_chat_id
        log.info(f"send_to_crm crm_chat_id {crm_chat_id}")

        # 1. Отправляем сообщение, при 401 — рефрешим и повторяем
        try:
            result = await provider.send_message(
                conversation_id=str(conversation_id), client_phone=client_phone, client_name=client_name,
                text=text, message_id=message_id, crm_chat_id=crm_chat_id, media=media)
            log.info(f"CRM result: {result}")
        except Exception as e:
            try:
                new_tokens = await provider.refresh_tokens()
                await self._uow.crm_accounts.update(conn, **new_tokens)
                conn.access_token_enc = new_tokens["access_token_enc"]
                conn.refresh_token_enc = new_tokens["refresh_token_enc"]
                result = await provider.send_message(
                    conversation_id=str(conversation_id), client_phone=client_phone, client_name=client_name,
                    text=text, message_id=message_id, crm_chat_id=crm_chat_id, media=media)
                log.info(f"CRM result after refresh: {result}")
            except Exception as e2:
                log.error("CRM send failed tenant=%s: %s", tenant_id, e2, exc_info=True)
                return

        log.info(f"send_to_crm result {result}")

        # --- AmoCRM ---
        if conn.crm_type == "amocrm":
            amo_chat_id = result.get("crm_chat_id", f"dc_{conversation_id}")
            await self._uow.conversations.update(conversation, crm_chat_id=amo_chat_id)
            log.info(f"send_to_crm amo_chat_id={amo_chat_id}")
            return amo_chat_id
        
        # --- Bitrix24 ---
        data_result = result.get("result", {}).get("DATA", {}).get("RESULT", [{}])
        session_chat_id = str(data_result[0].get("session", {}).get("CHAT_ID", ""))
        
        if session_chat_id and session_chat_id != conversation.crm_chat_id:
            await self._uow.conversations.update(conversation, crm_chat_id=session_chat_id)
            log.info(f"send_to_crm session_chat_id={session_chat_id}")
        
        try:
            bx = provider._client()
            contact_id = await bx.find_contact_by_phone(client_phone)
            log.info(f"find_contact_by_phone client_phone={client_phone} contact_id={contact_id}")
            if contact_id:
                deal_id = await bx.find_open_deal(contact_id)
                log.info(f"find_open_deal contact_id={contact_id} deal_id={deal_id}")
                if deal_id:
                    attach_result = await bx.attach_deal_to_chat(
                        session_chat_id,
                        conn.crm_line_id,
                        conn.connector_id,
                        deal_id,
                    )
                    log.info(f"attach_deal_to_chat result={attach_result}")
                else:
                    crm_settings = await self._uow.crm_settings.get_by_tenant(tenant_id)
                    log.info(
                        f"no deal found, crm_settings={crm_settings} "
                        f"no_deal_action={crm_settings.no_deal_action if crm_settings else None}"
                    )
            else:
                log.warning(f"contact not found for client_phone={client_phone}")
        except Exception as e:
            log.error("CRM contact/deal lookup failed: %s", e, exc_info=True)
        
        log.info(f"send_to_crm session_chat_id {session_chat_id}")
        return session_chat_id

    async def handle_webhook(self, tenant_id: uuid.UUID, crm_type: str, data: dict) -> dict:
        conn = await self._uow.crm_accounts.get_by_tenant(tenant_id, crm_type)
        if not conn:
            return {}
        provider = get_provider(conn)
        parsed = await provider.handle_webhook(data)
        parsed["crm_connection_id"] = conn.id
        return parsed

    async def _download_bitrix_media(self, data: dict) -> list[dict]:
        from services.storage_service import StorageService
        storage = StorageService()
        media = []
        i = 0
        while True:
            prefix = f"data[MESSAGES][0][message][files][{i}]"
            link = data.get(f"{prefix}[downloadLink]")
            if not link:
                break
            name = data.get(f"{prefix}[name]", f"file_{i}")
            mime = data.get(f"{prefix}[mime]", "application/octet-stream")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(link, timeout=30)
                    resp.raise_for_status()
                media_id = uuid.uuid4()
                await storage.save_file(resp.content, media_id, name, mime)
                media.append({"id": str(media_id), "file_name": name, "mime_type": mime})
            except Exception as e:
                log.error(f"_download_bitrix_media failed i={i}: {e}")
            i += 1
        return media

    async def _collect_bitrix_files(self, data: dict) -> list[tuple[bytes, str, str]]:
        files = []
        i = 0
        while True:
            prefix = f"data[MESSAGES][0][message][files][{i}]"
            link = data.get(f"{prefix}[downloadLink]")
            if not link:
                break
            name = data.get(f"{prefix}[name]", f"file_{i}")
            mime = data.get(f"{prefix}[mime]", "application/octet-stream")
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(link, timeout=30)
                    resp.raise_for_status()
                files.append((resp.content, name, mime))
                log.info(f"_collect_bitrix_files i={i} name={name}")
            except Exception as e:
                log.error(f"_collect_bitrix_files failed i={i}: {e}")
            i += 1
        return files

    async def handle_bitrix_incoming(self, data: dict) -> None:
        import re
        from infra.crypto import decrypt, encrypt
        from core.config import settings
        from crm.app.services.providers.bitrix.client import BitrixClient
        log.info(f"handle_bitrix_incoming full data: {data}")
        member_id = data.get("auth[member_id]")
        if not member_id:
            return
        connector_id = data.get("data[CONNECTOR]")
        conn = await self._uow.crm_accounts.get_by_member_and_connector(member_id, connector_id)
        log.info(f"handle_bitrix_incoming conn={conn} line_id={conn.line_id if conn else None}")
        if not conn or not conn.line_id:
            log.warning(f"handle_bitrix_incoming: no conn or line_id for member_id={member_id}")
            return
        account = await self._uow.crm_accounts.get_by_id(conn.crm_account_id)
        if not account:
            log.warning(f"handle_bitrix_incoming: no account for conn.crm_account_id={conn.crm_account_id}")
            return
        event = data.get("event")
        if event != "ONIMCONNECTORMESSAGEADD":
            return
        # рефреш токена
        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=account.domain,
                refresh_token=decrypt(account.refresh_token_enc),
                client_id=settings.BITRIX_CLIENT_ID,
                client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            await self._uow.crm_accounts.update(
                account,
                access_token_enc=encrypt(refreshed["access_token"]),
                refresh_token_enc=encrypt(refreshed["refresh_token"]),
            )
        except Exception as e:
            log.error(f"handle_bitrix_incoming token refresh failed: {e}")
            access_token = decrypt(account.access_token_enc)
        client_chat_id = data.get("data[MESSAGES][0][chat][id]")
        crm_chat_id = data.get("data[MESSAGES][0][im][chat_id]")
        text = data.get("data[MESSAGES][0][message][text]", "")
        text = re.sub(r'\[/?b\]|\[/?br\]', '', text).strip()
        WABA_TEMPLATES = {
            "disclaimer": {"name": "disclaimer", "language": "ru", "components": []},
            "first_welcome_messsage": {"name": "first_welcome_messsage", "language": "en", "components": [
                {"type": "body", "parameters": [{"type": "text", "text": "DoveChat"}]}]},
        }
        template_match = re.match(r'^\[template:(\w+)\]$', text)
        template = WABA_TEMPLATES.get(template_match.group(1)) if template_match else None

        convs = await self._uow.conversations.get_multi(
            filters={"line_id": conn.line_id, "crm_chat_id": crm_chat_id},
            limit=1,
        )
        if not convs:
            log.warning(f"handle_bitrix_incoming: no conv for crm_chat_id={crm_chat_id}")
            return
        conv = convs[0]
        files = await self._collect_bitrix_files(data)
        msg_json = MessageCreate(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            phone=conv.client_phone,
            text=text if not template else f"[template:{template['name']}]",
            status=MessageStatus.sent,
            template=template,
        ).model_dump_json()
        memberships = await self._uow.memberships.get_multi(
            filters={"tenant_id": account.tenant_id, "role": "owner"},
            limit=1,
        )
        owner = await self._uow.users.get_by_id(memberships[0].user_id)
        async with httpx.AsyncClient() as client:
            try:
                internal_url = "http://chat.dchat.svc.cluster.local:8001/v1/internal/crm-outgoing"
                params = {
                    "channel_type": conn.channel_type,
                    "user_id": str(owner.id),
                    "user_email": owner.email,
                }
                if files:
                    multipart = [("data", (None, msg_json, "application/json"))]
                    for content, name, mime in files:
                        multipart.append(("files", (name, content, mime)))
                    resp = await client.post(internal_url, files=multipart, data={
                        "channel_type": conn.channel_type,
                        "user_id": str(owner.id),
                        "user_email": owner.email,
                    }, timeout=10)
                else:
                    resp = await client.post(internal_url, data={
                        "data": msg_json,
                        "channel_type": conn.channel_type,
                        "user_id": str(owner.id),
                        "user_email": owner.email,
                    }, timeout=10)
                log.info(f"crm-outgoing response: {resp.status_code} {resp.text}")
            except Exception as e:
                log.error(f"crm-outgoing request failed: {e}")
        im_chat_id = data.get("data[MESSAGES][0][im][chat_id]")
        im_message_id = data.get("data[MESSAGES][0][im][message_id]")
        if crm_chat_id and im_message_id:
            try:
                bx = BitrixClient(domain=account.domain, access_token=access_token)
                await bx.call("imconnector.send.status.delivery", {
                    "CONNECTOR": conn.connector_id,
                    "LINE": conn.crm_line_id,
                    "MESSAGES[0][im][chat_id]": crm_chat_id,
                    "MESSAGES[0][im][message_id]": im_message_id,
                    "MESSAGES[0][message][id][0]": im_message_id,
                    "MESSAGES[0][chat][id]": client_chat_id,
                })
                log.info(f"delivery status sent for im_message_id={im_message_id}")
            except Exception as e:
                log.error(f"delivery status failed: {e}")

    async def _register_robots(self, bx) -> None:
        from core.config import settings

        for robot_code, robot_name in [
            ("dovechat_send_text", "DoveChat: Отправить текст"),
            ("dovechat_send_file", "DoveChat: Отправить файл"),
            ("dovechat_check_account", "DoveChat: Проверить аккаунт"),
        ]:
            try:
                await bx.call("bizproc.robot.delete", {"CODE": robot_code})
            except Exception:
                pass

            if robot_code == "dovechat_check_account":
                return_properties = {
                    "exists": {"Name": "Зарегистрирован", "Type": "bool", "Multiple": "N"},
                    "user_id": {"Name": "ID пользователя", "Type": "string", "Multiple": "N"},
                    "error": {"Name": "Ошибка", "Type": "string", "Multiple": "N"},
                }
            else:
                return_properties = {
                    "status": {"Name": "Статус", "Type": "string", "Multiple": "N"},
                    "message_id": {"Name": "ID сообщения", "Type": "string", "Multiple": "N"},
                    "error": {"Name": "Ошибка", "Type": "string", "Multiple": "N"},
                }

            properties = {
                "phone": {
                    "Name": "Телефон клиента",
                    "Type": "string",
                    "Required": "Y",
                    "Multiple": "N",
                },
                "line_id": {
                    "Name": "ID линии",
                    "Type": "string",
                    "Required": "Y",
                    "Multiple": "N",
                },
                "text": {
                    "Name": "Текст сообщения",
                    "Type": "text",
                    "Required": "Y" if robot_code == "dovechat_send_text" else "N",
                    "Multiple": "N",
                },
            }
            if robot_code == "dovechat_send_file":
                properties["file_url"] = {
                    "Name": "Ссылка на файл",
                    "Type": "string",
                    "Required": "Y",
                    "Multiple": "N",
                }
                properties["file_name"] = {
                    "Name": "Имя файла",
                    "Type": "string",
                    "Required": "N",
                    "Multiple": "N",
                }
            if robot_code == "dovechat_check_account":
                properties.pop("text", None)

            try:
                await bx.call(
                    "bizproc.robot.add",
                    {
                        "CODE": robot_code,
                        "HANDLER": f"{settings.host_url}/crm/api/v1/robots/{robot_code}",
                        "AUTH_USER_ID": 1,
                        "USE_SUBSCRIPTION": "Y",
                        "NAME": robot_name,
                        "PROPERTIES": properties,
                        "RETURN_PROPERTIES": return_properties,
                        "FILTER": {
                            "INCLUDE": [
                                ["crm", "CCrmDocumentDeal"],
                                ["crm", "CCrmDocumentLead"],
                                ["crm", "CCrmDocumentContact"],
                            ]
                        },
                    },
                    use_json=True,
                )
                log.info(f"robot registered: {robot_code}")
            except Exception as e:
                log.warning(f"bizproc.robot.add {robot_code} failed: {e}")

        try:
            await bx.call(
                "crm.userfield.add",
                {
                    "fields": {
                        "ENTITY_ID": "CRM_DEAL",
                        "FIELD_NAME": "DOVECHAT_WA_TG_STATUS",
                        "USER_TYPE_ID": "string",
                        "XML_ID": "DOVECHAT_WA_TG_STATUS",
                        "EDIT_FORM_LABEL": "DoveChat: статус в мессенджере",
                        "LIST_COLUMN_LABEL": "DoveChat: статус",
                        "MANDATORY": "N",
                    }
                },
            )
            log.info("crm.userfield.add DOVECHAT_WA_TG_STATUS done")
        except Exception as e:
            log.warning(f"crm.userfield.add failed (possibly already exists): {e}")


    async def save_install_tokens(self, body: bytes, domain: str = "" ) -> None:
        from urllib.parse import parse_qs
        from core.config import settings
        from infra.crypto import decrypt, encrypt
    
        parsed = parse_qs(body.decode())
        data = {k: v[0] for k, v in parsed.items()}

        app_token = data.get("APPLICATION_TOKEN")
        log.info(f"onappinstall app_token={app_token}")
        log.info(f"onappinstall data={data}")

        # if app_token != settings.BITRIX_APPLICATION_TOKEN:
        #    log.warning(f"onappinstall: bad application_token expected={settings.BITRIX_APPLICATION_TOKEN}")
        #   return

        log.info(f"\n\n if event  ONAPPINSTALL \n\n")

        access_token = data.get("AUTH_ID")
        refresh_token = data.get("REFRESH_ID")
        member_id = data.get("member_id")
        domain = data.get("auth[domain]") or domain

        log.info(f"\n\n member_id  {member_id} domain {domain}\n\n")
    
        if not all([access_token, refresh_token, member_id, domain]):
            log.info(f"\n\n if not all \n\n")
            log.warning("onappinstall: missing auth fields")
            return

        rows = await self._uow.crm_accounts.get_multi(filters={"domain": domain}, limit=1)
        conn = rows[0] if rows else None

        log.info(f"save_install_tokens updating conn member_id={member_id} domain={domain}")
        if conn:
            log.info(f"save_install_tokens updating conn if conn member_id={member_id} domain={domain}")
            await self._uow.crm_accounts.update(
                conn,
                member_id=member_id,
                access_token_enc=encrypt(access_token),
                refresh_token_enc=encrypt(refresh_token),
                bitrix_application_token_enc=encrypt(app_token),
            )
        else:
            await self._uow.crm_accounts.create(
                crm_type="bitrix24",
                domain=domain,
                member_id=member_id,
                access_token_enc=encrypt(access_token),
                refresh_token_enc=encrypt(refresh_token),
                is_active=True,
                bitrix_application_token_enc=encrypt(app_token),
            )

        from crm.app.services.providers.bitrix.client import BitrixClient
        from core.config import settings
        bx = BitrixClient(domain=domain, access_token=access_token)
        for connector_id in settings.BITRIX_CONNECTOR_MAP.values():
            connector_name = settings.BITRIX_CONNECTOR_NAMES.get(connector_id, connector_id)
            log.info(f"register_connector iteration: {connector_id} name={connector_name} ")
            try:
                await bx.register_connector(connector_id, name=connector_name)
            except Exception as e:
                log.warning(f"register_connector {connector_id} failed: {e}")

        log.info("register_connector loop done")

        try:
            await bx.call("event.unbind", {
                "event": "ONIMCONNECTORMESSAGEADD",
                "handler": f"{settings.host_url}/crm/api/v1/webhooks/bitrix",
            })
        except Exception as e:
            log.warning(f"event.unbind: {e}")
        result = await bx.call("event.bind", {
            "event": "ONIMCONNECTORMESSAGEADD",
            "handler": f"{settings.host_url}/crm/api/v1/webhooks/bitrix",
            "auth_type": 1,
        })
        log.info(f"event.bind result: {result}")

        await self._register_robots(bx)
        return data.get("PLACEMENT") == "SETTING_CONNECTOR", data.get("auth[domain]") or domain

    async def get_lines_for_bitrix(self, email: str, password: str, bx_auth: dict) -> dict:
        import httpx
        ACCOUNT_URL = "http://account.dchat.svc.cluster.local:8071"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(f"{ACCOUNT_URL}/api/v1/auth/login",
                                         data={"username": email, "password": password})
            if resp.status_code != 200:
                return {"error": "Неверный email или пароль"}
            jwt_token = resp.json().get("access_token")
        except Exception as e:
            log.error(f"get_lines_for_bitrix: login error {e}")
            return {"error": "Ошибка подключения к серверу"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{ACCOUNT_URL}/api/v1/tenant/",
                                        headers={"Authorization": f"Bearer {jwt_token}"})
            tenants = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            log.error(f"get_lines_for_bitrix: tenants error {e}")
            tenants = []
        return {
            "tenants": tenants,
            "jwt_token": jwt_token,
            "bx_auth": bx_auth,
        }

    async def connect_line(self, line_id: uuid.UUID, bx_auth: dict) -> dict:
        from infra.crypto import decrypt, encrypt
        from core.config import settings
        from crm.app.services.providers.bitrix.client import BitrixClient

        domain = bx_auth.get("domain", "")
        member_id = bx_auth.get("member_id", "")
        access_token = bx_auth.get("access_token", "")
        refresh_token = bx_auth.get("refresh_token", "")

        rows = await self._uow.crm_accounts.get_multi(filters={"domain": domain}, limit=1)
        account = rows[0] if rows else None

        log.warning(
            f"connect_line domain={domain} token_len={len(access_token)} token_start={access_token[:15]!r} account_existing={bool(account)} refresh_token_start={refresh_token[:15]!r}")

        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=domain, refresh_token=refresh_token,
                client_id=settings.BITRIX_CLIENT_ID, client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            refresh_token = refreshed["refresh_token"]
        except Exception as e:
            log.error(f"connect_line token refresh failed: {e}")
            return {"error": "Ошибка обновления токена Битрикс"}

        line = await self._uow.lines.get_by_id(line_id)
        if not line:
            return {"error": "Линия не найдена"}

        if account:
            await self._uow.crm_accounts.update(
                account,
                tenant_id=line.tenant_id,
                access_token_enc=encrypt(access_token),
                refresh_token_enc=encrypt(refresh_token),
                member_id=member_id,
                is_active=True,
            )
        else:
            account = await self._uow.crm_accounts.create(
                tenant_id=line.tenant_id,
                crm_type="bitrix24",
                domain=domain,
                member_id=member_id,
                access_token_enc=encrypt(access_token),
                refresh_token_enc=encrypt(refresh_token),
                is_active=True,
            )

        bx = BitrixClient(domain=domain, access_token=access_token)

        connector_id = bx_auth.get("connector")
        channel_type_val = next(
            (k for k, v in settings.BITRIX_CONNECTOR_MAP.items() if v == connector_id), None
        )
        if not channel_type_val:
            return {"error": f"Неподдерживаемый коннектор: {connector_id}"}

        reg_result = await bx.register_connector(connector_id)
        log.info(f"register_connector result: {reg_result}")

        rows = await self._uow.crm_line_connections.get_multi(
            filters={"line_id": line_id, "connector_id": connector_id}, limit=1
        )
        line_conn = rows[0] if rows else None

        crm_line_id = (
                bx_auth.get("bx_line_id")
                or (line_conn.crm_line_id if line_conn else None)
                or await bx.create_open_line(line.name)
        )
        log.info(
            f"connect_line crm_line_id={crm_line_id!r} member_id={member_id} connector_id={connector_id} line_conn={line_conn}"
        )

        link_result = await bx.link_connector(crm_line_id, connector_id)
        log.info(f"link_connector result: {link_result}")
        activate_result = await bx.activate_connector(crm_line_id, connector_id)
        log.info(f"activate_connector result: {activate_result}")

        if line_conn:
            await self._uow.crm_line_connections.update(
                line_conn,
                crm_account_id=account.id,
                channel_type=channel_type_val,
                connector_id=connector_id,
                crm_line_id=crm_line_id,
                is_active=True,
            )
        else:
            await self._uow.crm_line_connections.create(
                crm_account_id=account.id,
                line_id=line_id,
                channel_type=channel_type_val,
                connector_id=connector_id,
                crm_line_id=crm_line_id,
                is_active=True,
            )

        return {"line_name": line.name}


    async def get_lines_for_tenant(self, jwt_token: str, tenant_id: str, bx_auth: dict) -> dict:
        import httpx
        ACCOUNT_URL = "http://account.dchat.svc.cluster.local:8071"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{ACCOUNT_URL}/api/v1/auth/switch-tenant",
                    params={"tenant_id": tenant_id},
                    headers={"Authorization": f"Bearer {jwt_token}"},
                )
            if resp.status_code != 200:
                return {"error": "Ошибка переключения компании"}
            tenant_token = resp.json().get("access_token")
        except Exception as e:
            log.error(f"get_lines_for_tenant: switch error {e}")
            return {"error": "Ошибка подключения к серверу"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{ACCOUNT_URL}/api/v1/tenants/{tenant_id}/lines/",
                    headers={"Authorization": f"Bearer {tenant_token}"})
            lines = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            log.error(f"get_lines_for_tenant: lines error {e}")
            lines = []
        return {"lines": lines, "bx_auth": bx_auth}

    async def handle_onappinstall(self, body: bytes, domain: str = ""):
        await self.save_install_tokens(body, domain=domain)
        import json
        from urllib.parse import parse_qs
        from fastapi.responses import RedirectResponse
        parsed = parse_qs(body.decode())
        data = {k: v[0] for k, v in parsed.items()}
        if data.get("PLACEMENT") == "SETTING_CONNECTOR":
            domain_val = data.get("auth[domain]") or domain
            access_token = data.get("AUTH_ID", "")
            refresh_token = data.get("REFRESH_ID", "")
            member_id = data.get("member_id", "")
            connector = ""
            line = ""
            placement_options = data.get("PLACEMENT_OPTIONS", "")
            if placement_options:
                try:
                    opts = json.loads(placement_options)
                    connector = opts.get("CONNECTOR", "")
                    line = opts.get("LINE", "")
                except Exception:
                    pass
            return RedirectResponse(
                url=(
                    f"{settings.host_url}/crm/api/v1/install/bitrix?DOMAIN={domain_val}"
                    f"&ACCESS_TOKEN={access_token}"
                    f"&REFRESH_TOKEN={refresh_token}"
                    f"&MEMBER_ID={member_id}"
                    f"&CONNECTOR={connector}"
                    f"&LINE={line}"
                ),
                status_code=303,
            )
        return RedirectResponse(url="/crm/html/install_finish.html", status_code=303)

    async def get_lines_for_member(self, member_id: str) -> dict:
        conn = await self._uow.crm_accounts.get_by_member_id(member_id)
        if not conn:
            return {"lines": []}
        line = await self._uow.lines.get_by_id(conn.line_id)
        if not line:
            return {"lines": []}
        channels = await self._uow.channel_accounts.get_multi(
            filters={"line_id": conn.line_id},
        )
        return {"lines": [{"id": str(line.id), "name": line.name, "channels": [
            {"id": str(c.id),
             "channel_type": c.channel_type.value if hasattr(c.channel_type, "value") else c.channel_type}
            for c in channels
        ]}]}
    
    async def start_outgoing(self, member_id: str, contact_id: str, line_id: uuid.UUID, channel_account_id: uuid.UUID, text: str) -> dict:
        import httpx
        from infra.crypto import decrypt, encrypt
        from core.config import settings
        from crm.app.services.providers.bitrix.client import BitrixClient
    
        conn = await self._uow.crm_accounts.get_by_member_id(member_id)
        if not conn:
            return {"error": "Подключение не найдено"}
    
        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=conn.domain,
                refresh_token=decrypt(conn.refresh_token_enc),
                client_id=settings.BITRIX_CLIENT_ID,
                client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            await self._uow.crm_accounts.update(
                conn,
                access_token_enc=encrypt(refreshed["access_token"]),
                refresh_token_enc=encrypt(refreshed["refresh_token"]),
            )
        except Exception as e:
            log.error(f"start_outgoing token refresh failed: {e}")
            access_token = decrypt(conn.access_token_enc)
    
        bx = BitrixClient(domain=conn.domain, access_token=access_token)
        phone = await bx.get_contact_phone(contact_id)
        if not phone:
            return {"error": "Телефон контакта не найден"}
    
        line = await self._uow.lines.get_by_id(line_id)
        if not line:
            return {"error": "Линия не найдена"}
    
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    "http://chat.dchat.svc.cluster.local:8001/v1/internal/crm-outgoing",
                    json={
                        "line_id": str(line_id),
                        "client_phone": phone,
                        "text": text,
                        "crm_connection_id": str(conn.id),
                        "contact_id": contact_id,
                        "crm_line_id": conn.crm_line_id,
                        "connector_id": conn.connector_id,
                        "channel_type": conn.channel_type,
                        "channel_account_id": str(channel_account_id) if channel_account_id else None
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    return {"error": "Ошибка отправки сообщения"}
                return resp.json()
            except Exception as e:
                log.error(f"start_outgoing crm-outgoing failed: {e}")
                return {"error": "Ошибка соединения с чат-сервисом"}

    async def handle_robot(self, robot_code: str, data: dict) -> dict:
        from infra.crypto import decrypt, encrypt
        from core.config import settings
        from crm.app.services.providers.bitrix.client import BitrixClient

        event_token = data.get("event_token") or data.get("EVENT_TOKEN")
        member_id = data.get("auth[member_id]")
        phone = data.get("properties[phone]") or data.get("PROPERTIES[phone]")
        line_id_str = data.get("properties[line_id]") or data.get("PROPERTIES[line_id]")

        log.info(f"handle_robot code={robot_code} member_id={member_id} phone={phone} line_id={line_id_str}")

        if not all([event_token, member_id, phone, line_id_str]):
            log.error(
                f"handle_robot missing fields: event_token={event_token} member_id={member_id} phone={phone} line_id={line_id_str}")
            return {"status": "error"}

        conn = await self._uow.crm_accounts.get_by_member_id(member_id)
        if not conn:
            log.error(f"handle_robot no connection for member_id={member_id}")
            return {"status": "error"}

        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=conn.domain,
                refresh_token=decrypt(conn.refresh_token_enc),
                client_id=settings.BITRIX_CLIENT_ID,
                client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            await self._uow.crm_accounts.update(
                conn,
                access_token_enc=encrypt(refreshed["access_token"]),
                refresh_token_enc=encrypt(refreshed["refresh_token"]),
            )
        except Exception as e:
            log.error(f"handle_robot token refresh failed: {e}")
            access_token = decrypt(conn.access_token_enc)

        try:
            line_id = uuid.UUID(line_id_str)
        except ValueError:
            log.error(f"handle_robot invalid line_id: {line_id_str}")
            return {"status": "error"}

        bx = BitrixClient(domain=conn.domain, access_token=data.get("auth[application_token]"))

        if robot_code == "dovechat_check_account":
            return_values = await self._robot_check_account(phone, line_id)
            log.info(f"robot dovechat_check_account return_values {return_values}")
        else:
            return_values = await self._robot_send(robot_code, data, conn, line_id, phone)

        try:
            log_message = return_values.get("error") or "Получен ответ от приложения."

            await bx.call(
                "bizproc.event.send",
                {
                    "event_token": event_token,
                    "RETURN_VALUES": return_values,
                    "LOG_MESSAGE": log_message,
                },
            )
            log.info(f"handle_robot bizproc.event.send done code={robot_code}")
        except Exception as e:
            log.error(f"handle_robot bizproc.event.send failed: {e}")

        return {"status": "ok"}

    async def _robot_send(self, robot_code: str, data: dict, conn, line_id: uuid.UUID, phone: str) -> dict:
        import time
        text = data.get("properties[text]") or data.get("PROPERTIES[text]") or ""
        file_url = data.get("properties[file_url]") or data.get("PROPERTIES[file_url]")
        file_name = data.get("properties[file_name]") or data.get("PROPERTIES[file_name]") or "file"

        started_at = time.monotonic()
        status = "error"
        message_id = ""
        error_msg = ""

        try:
            payload: dict = {
                "line_id": str(line_id),
                "client_phone": phone,
                "text": text,
                "crm_connection_id": str(conn.id),
                "contact_id": "",
                "crm_line_id": conn.crm_line_id,
                "connector_id": conn.connector_id,
                "channel_type": conn.channel_type,
                "channel_account_id": None,
                "media": [],
            }

            if robot_code == "dovechat_send_file" and file_url:
                from services.storage_service import StorageService
                import uuid as _uuid
                storage = StorageService()
                async with httpx.AsyncClient() as client:
                    resp = await client.get(file_url, timeout=30)
                    resp.raise_for_status()
                log.info(f"_robot_send file downloaded: {file_url} status={resp.status_code}")
                media_id = _uuid.uuid4()
                mime = resp.headers.get("content-type", "application/octet-stream").split(";")[0]
                await storage.save_file(resp.content, media_id, file_name, mime)
                payload["media"] = [{"id": str(media_id), "file_name": file_name, "mime_type": mime}]

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "http://chat.dchat.svc.cluster.local:8001/v1/internal/crm-robot-send",
                    json=payload,
                    timeout=15,
                )
                log.info(f"_robot_send crm-robot-send resp: {resp.status_code} {resp.text}")
                result = resp.json()

            if result.get("status") == "ok" or result.get("conversation_id"):
                status = "ok"
                message_id = result.get("message_id", result.get("conversation_id", ""))
            else:
                error_msg = result.get("error", "unknown error")

        except Exception as e:
            log.error(f"_robot_send failed: {e}")
            error_msg = str(e)

        duration_ms = int((time.monotonic() - started_at) * 1000)
        log.info(f"_robot_send done code={robot_code} status={status} duration={duration_ms}ms")

        return {"status": status, "message_id": message_id, "error": error_msg}

    async def _robot_check_account(self, phone: str, line_id: uuid.UUID) -> dict:
        from models.lines import ChannelType
        res = None
        accounts = await self._uow.channel_accounts.get_multi(
            filters={"line_id": line_id, "channel_type": ChannelType.telegram_user},
            limit=1,
        )
        if accounts and accounts[0].session_string:
            session_string = accounts[0].session_string
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "http://tg-connector.dchat.svc.cluster.local:8000/prod/check-phone",
                        json={"phone": phone, "session_string": session_string},
                        timeout=15,
                    )
                    log.info(f"_robot_check_account resp: {resp.status_code} {resp.text}")
                    result = resp.json()
                exists = "Y" if result.get("exists") else "N"
                user_id = str(result.get("user_id") or "")
                res = {"exists": exists, "user_id": user_id, "error": ""}
            except Exception as e:
                log.error(f"_robot_check_account failed: {e}")
                res = {"exists": "N", "user_id": "", "error": str(e)}
        else:
            wa_accounts = await self._uow.channel_accounts.get_multi(
                filters={"line_id": line_id, "channel_type": ChannelType.whatsapp_green},
                limit=1,
            )
            if not wa_accounts:
                log.error(f"_robot_check_account no channel account for line_id={line_id}")
                res = {"exists": "N", "user_id": "", "error": "Нет активного канала"}
            else:
                from infra.crypto import decrypt
                creds = json.loads(decrypt(wa_accounts[0].credentials_encrypted["encrypted_data"]))
                id_instance = creds.get("id_instance")
                api_token = creds.get("api_token")
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{settings.proxy_green_url}/waInstance{id_instance}/checkWhatsapp/{api_token}",
                            json={"phoneNumber": int(phone)},
                            timeout=15,
                        )
                        log.info(f"_robot_check_account wa resp: {resp.status_code} {resp.text}")
                        result = resp.json()
                    exists = "Y" if result.get("existsWhatsapp") else "N"
                    res = {"exists": exists, "user_id": "", "error": ""}
                except Exception as e:
                    log.error(f"_robot_check_account wa failed: {e}")
                    res = {"exists": "N", "user_id": "", "error": str(e)}
        return {"exists": "Y" if res["exists"] == "Y" else "N"}

    async def check_wa_tg(self, data: dict) -> dict:
        from crm.app.services.providers.bitrix.client import BitrixClient
        from infra.crypto import decrypt, encrypt
        from core.config import settings

        member_id = data.get("auth[member_id]")
        deal_id = data.get("data[FIELDS][ID]")
        domain = data.get("auth[domain]")

        if not all([member_id, deal_id, domain]):
            log.error(f"check_wa_tg missing fields: {data}")
            return {"status": "error"}

        conn = await self._uow.crm_accounts.get_by_member_id(member_id)
        if not conn:
            log.error(f"check_wa_tg no conn for member_id={member_id}")
            return {"status": "error"}

        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=domain,
                refresh_token=decrypt(conn.refresh_token_enc),
                client_id=settings.BITRIX_CLIENT_ID,
                client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            await self._uow.crm_accounts.update(
                conn,
                access_token_enc=encrypt(refreshed["access_token"]),
                refresh_token_enc=encrypt(refreshed["refresh_token"]),
            )
        except Exception as e:
            log.error(f"check_wa_tg token refresh failed: {e}")
            access_token = decrypt(conn.access_token_enc)

        bx = BitrixClient(domain=domain, access_token=access_token)

        try:
            deal = await bx.call("crm.deal.get", {"id": deal_id})
            contact_id = deal.get("result", {}).get("CONTACT_ID")
            if not contact_id or contact_id == "0":
                log.warning(f"check_wa_tg no contact for deal_id={deal_id}")
                return {"status": "no_contact"}
            contact = await bx.call("crm.contact.get", {"id": contact_id})
            phones = contact.get("result", {}).get("PHONE", [])
            phone = phones[0].get("VALUE") if phones else None
            log.info(f"check_wa_tg deal_id={deal_id} contact_id={contact_id} phone={phone}")
        except Exception as e:
            log.error(f"check_wa_tg crm fetch failed: {e}")
            return {"status": "error"}

        if not phone:
            log.warning(f"check_wa_tg no phone contact_id={contact_id}")
            return {"status": "no_phone"}

        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        result = await self._robot_check_account(phone, conn.line_id)
        exists = result.get("exists") == "Y"
        status_text = "Есть в мессенджере" if exists else "Нет в мессенджере"

        try:
            await bx.call(
                "crm.deal.update",
                {"id": deal_id, "fields": {"UF_CRM_1781704941990": status_text}},
                use_json=True,
            )
            log.info(f"check_wa_tg updated deal_id={deal_id} status={status_text}")
        except Exception as e:
            log.error(f"check_wa_tg deal update failed: {e}")

        return {"status": "ok", "exists": exists}

    
    
    async def check_wa_tg(self, data: dict) -> dict:
        from crm.app.services.providers.bitrix.client import BitrixClient
        from infra.crypto import decrypt, encrypt
        from core.config import settings
    
        member_id = data.get("auth[member_id]")
        deal_id = data.get("data[FIELDS][ID]")
        domain = data.get("auth[domain]")
    
        if not all([member_id, deal_id, domain]):
            log.error(f"check_wa_tg missing fields: {data}")
            return {"status": "error"}
    
        conn = await self._uow.crm_accounts.get_by_member_id(member_id)
        if not conn:
            log.error(f"check_wa_tg no conn for member_id={member_id}")
            return {"status": "error"}
    
        try:
            refreshed = await BitrixClient.refresh_tokens(
                domain=domain,
                refresh_token=decrypt(conn.refresh_token_enc),
                client_id=settings.BITRIX_CLIENT_ID,
                client_secret=settings.BITRIX_CLIENT_SECRET,
            )
            access_token = refreshed["access_token"]
            await self._uow.crm_accounts.update(
                conn,
                access_token_enc=encrypt(refreshed["access_token"]),
                refresh_token_enc=encrypt(refreshed["refresh_token"]),
            )
        except Exception as e:
            log.error(f"check_wa_tg token refresh failed: {e}")
            access_token = decrypt(conn.access_token_enc)
    
        bx = BitrixClient(domain=domain, access_token=access_token)
    
        try:
            deal = await bx.call("crm.deal.get", {"id": deal_id})
            contact_id = deal.get("result", {}).get("CONTACT_ID")
            if not contact_id or contact_id == "0":
                log.warning(f"check_wa_tg no contact for deal_id={deal_id}")
                return {"status": "no_contact"}
            contact = await bx.call("crm.contact.get", {"id": contact_id})
            phones = contact.get("result", {}).get("PHONE", [])
            phone = phones[0].get("VALUE") if phones else None
            log.info(f"check_wa_tg deal_id={deal_id} contact_id={contact_id} phone={phone}")
        except Exception as e:
            log.error(f"check_wa_tg crm fetch failed: {e}")
            return {"status": "error"}
    
        if not phone:
            log.warning(f"check_wa_tg no phone contact_id={contact_id}")
            return {"status": "no_phone"}
    
        phone = phone.replace("+", "").replace(" ", "").replace("-", "")
        result = await self._robot_check_account(phone, conn.line_id)
        exists = result.get("exists") == "Y"
        status_text = "Есть в мессенджере" if exists else "Нет в мессенджере"
    
        try:
            await bx.call(
                "crm.deal.update",
                {"id": deal_id, "fields": {"UF_CRM_1781704941990": status_text}},
                use_json=True,
            )
            log.info(f"check_wa_tg updated deal_id={deal_id} status={status_text}")
        except Exception as e:
            log.error(f"check_wa_tg deal update failed: {e}")
    
        return {"status": "ok", "exists": exists}

    async def handle_amo_install(self, code: str, domain: str) -> dict:
        from fastapi.responses import RedirectResponse
        from core.config import settings
        from infra.crypto import encrypt
        import httpx
    
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://{domain}/oauth2/access_token",
                json={
                    "client_id": settings.AMO_CLIENT_ID,
                    "client_secret": settings.AMO_CLIENT_SECRET,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.AMO_REDIRECT_URI,
                },
            )
            log.info(f"handle_amo_install token exchange domain={domain} status={resp.status_code}")
            resp.raise_for_status()
            tokens = resp.json()
    
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
    
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"https://{domain}/api/v4/account",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            log.info(f"handle_amo_install get account domain={domain} status={resp.status_code}")
            resp.raise_for_status()
            account = resp.json()
    
        account_id = str(account["id"])
        amojo_id = account.get("amojo_id", "")
    
        await self._uow.crm_accounts.upsert_amo(
            domain=domain,
            account_id=account_id,
            amojo_id=amojo_id,
            access_token_enc=encrypt(access_token),
            refresh_token_enc=encrypt(refresh_token),
        )
        log.info(f"handle_amo_install saved domain={domain} account_id={account_id}")
        return RedirectResponse(url="/crm/html/install_finish.html", status_code=303)

    async def handle_amo_incoming(self, body: bytes, amojo_id: str, signature: str) -> None:
        from crm.app.services.providers.amocrm.client import AmoCrmClient
        from core.config import settings
        import json

        conn = await self._uow.crm_accounts.get_by_amojo_id(amojo_id)
        if not conn:
            log.error(f"handle_amo_incoming: connection not found amojo_id={amojo_id}")
            return

        line_conns = await self._uow.crm_line_connections.get_by_account(conn.id)
        if not line_conns:
            log.warning(f"handle_amo_incoming: no line connection for account {conn.id}")
            return

        client = AmoCrmClient(
            channel_id=settings.AMO_CHANNEL_ID,
            channel_secret=settings.AMO_CHANNEL_SECRET,
            account_id=conn.amojo_id,
        )
        if not client.verify_webhook(body, signature):
            log.error(f"handle_amo_incoming: invalid signature amojo_id={amojo_id}")
            return

        data = json.loads(body)
        log.info(f"handle_amo_incoming data={data}")
        provider = AmoCrmProvider(conn)
        parsed = await provider.handle_webhook(data)
        log.info(f"handle_amo_incoming parsed={parsed} amojo_id={amojo_id}")

        crm_chat_id = parsed["crm_chat_id"]
        link = await self._uow.crm_dialog_links.get_by_crm_chat_id(crm_chat_id)
        if not link:
            line_id = line_conns[0].line_id
            convs = await self._uow.conversations.get_multi(
                filters={"client_phone": parsed["client_phone"], "line_id": line_id},
                limit=1,
            )
            if not convs:
                log.warning(f"handle_amo_incoming: no conversation phone={parsed['client_phone']} line={line_id}")
                return
            link = await self._uow.crm_dialog_links.create(
                conversation_id=convs[0].id,
                crm_account_id=conn.id,
                crm_chat_id=crm_chat_id,
                crm_user_id=parsed["client_phone"],
            )

        conv = await self._uow.conversations.get_by_id(link.conversation_id)
        if not conv:
            log.error(f"handle_amo_incoming: no conversation id={link.conversation_id}")
            return

        memberships = await self._uow.memberships.get_multi(
            filters={"tenant_id": conn.tenant_id, "role": "owner"},
            limit=1,
        )
        owner = await self._uow.users.get_by_id(memberships[0].user_id)

        msg_json = MessageCreate(
            conversation_id=conv.id,
            direction=MessageDirection.outbound,
            phone=conv.client_phone,
            text=parsed["text"],
            status=MessageStatus.sent,
        ).model_dump_json()

        async with httpx.AsyncClient() as http:
            try:
                resp = await http.post(
                    "http://chat.dchat.svc.cluster.local:8001/v1/internal/crm-outgoing",
                    data={
                        "data": msg_json,
                        "channel_type": line_conns[0].channel_type,
                        "user_id": str(owner.id),
                        "user_email": owner.email,
                    },
                    timeout=10,
                )
                log.info(f"handle_amo_incoming crm_chat_id={crm_chat_id} status={resp.status_code}")
            except Exception as e:
                log.error(f"handle_amo_incoming request failed: {e}")
    
    async def amo_connect_channel(self, tenant_id: uuid.UUID) -> dict:
        from crm.app.services.providers.amocrm.client import AmoCrmClient
        from core.config import settings
    
        conn = await self._uow.crm_accounts.get_by_tenant(
            tenant_id=tenant_id,
            crm_type="amocrm",
        )
        if not conn:
            raise ValueError(f"No amocrm connection for tenant_id={tenant_id}")
    
        client = AmoCrmClient(
            channel_id=settings.AMO_CHANNEL_ID,
            channel_secret=settings.AMO_CHANNEL_SECRET,
            account_id=conn.amojo_id,
        )
        result = await client.connect_account()
        await self._uow.crm_accounts.update(
            conn,
            amojo_id=result.get("account_id"),
        )
        log.info(f"amo_connect_channel tenant_id={tenant_id} result={result}")
        return result


    async def disconnect_amo_line(self, line_id: uuid.UUID) -> None:
        conn = await self._uow.crm_line_connections.get_by_line(line_id)
        if conn:
            await self._uow.crm_line_connections.delete(conn)


    async def list_amo_accounts(self) -> list:
        return await self._uow.crm_accounts.get_multi(
            filters={"crm_type": "amocrm", "is_active": True},
        )
    
    async def connect_amo_line(self, body: AmoLineConnectRequest) -> dict:
        existing = await self._uow.crm_line_connections.get_multi(
            filters={"line_id": body.line_id, "is_active": True},
            limit=1,
        )
        if existing:
            await self._uow.crm_line_connections.update(
                existing[0],
                crm_account_id=body.crm_account_id,
                channel_type=body.channel_type,
            )
        else:
            await self._uow.crm_line_connections.create(
                crm_account_id=body.crm_account_id,
                line_id=body.line_id,
                channel_type=body.channel_type,
                is_active=True,
            )
        # await self._uow.commit()
        log.info(f"connect_amo_line line_id={body.line_id} crm_account_id={body.crm_account_id}")
        return {"ok": True}

    async def get_conv_by_lead(self, lead_id: str) -> uuid.UUID:
        links = await self._uow.crm_dialog_links.get_multi(filters={"amo_lead_id": lead_id}, limit=1)
        link = links[0] if links else None
        if link:
            convs = await self._uow.conversations.get_multi(filters={"id": link.conversation_id}, limit=1)
            conversation = convs[0] if convs else None
            lines = await self._uow.lines.get_multi(filters={"id": conversation.line_id}, limit=1)
            line = lines[0] if lines else None
            embed_token = jwt.encode(
                {
                    "sub": "970fb0f9-fbb4-46b3-8153-0c59f7ac883f",
                    "tenant_id": str(line.tenant_id),
                    "role": "owner",
                    "type": "access",
                    "exp": int(time.time()) + 8 * 3600,
                },
                settings.secret_key,
                algorithm=settings.algorithm,
            )
            return link.conversation_id, embed_token
        accounts = await self._uow.crm_accounts.get_multi(filters={"crm_type": "amocrm"})
        for account in accounts:
            provider = AmoCrmProvider(account)
            phone = await provider.get_lead_contact_phone(
                domain=account.domain,
                access_token=decrypt(account.access_token_enc),
                lead_id=lead_id,
            )
            convs = await self._uow.conversations.get_multi(filters={"client_phone": phone}, limit=1) if phone else []
            conversation = convs[0] if convs else None
            if not conversation:
                continue
            existing_links = await self._uow.crm_dialog_links.get_multi(filters={"conversation_id": conversation.id},
                                                                        limit=1)
            existing_link = existing_links[0] if existing_links else None
            if existing_link:
                await self._uow.crm_dialog_links.update(existing_link, amo_lead_id=lead_id)
            lines = await self._uow.lines.get_multi(filters={"id": conversation.line_id}, limit=1)
            line = lines[0] if lines else None
            embed_token = jwt.encode(
                {
                    "sub": "970fb0f9-fbb4-46b3-8153-0c59f7ac883f",
                    "tenant_id": str(line.tenant_id),
                    "role": "owner",
                    "type": "access",
                    "exp": int(time.time()) + 8 * 3600,
                },
                settings.secret_key,
                algorithm=settings.algorithm,
            )
            return conversation.id, embed_token
        raise HTTPException(status_code=404, detail="conversation not found for lead")
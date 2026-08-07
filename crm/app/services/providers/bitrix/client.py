"""Bitrix24 REST API client."""
import uuid
import httpx
import logging
from datetime import datetime, timezone
from core.config import settings

log = logging.getLogger("uvicorn.error")

class BitrixClient:
    def __init__(self, domain: str, access_token: str):
        self.domain = domain
        self.access_token = access_token

    async def call(self, method: str, params: dict, use_json: bool = False) -> dict:
        url = f"https://{self.domain}/rest/{method}.json?auth={self.access_token}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=params if use_json else None, data=None if use_json else params)
            if not resp.is_success:
                log.error(f"Bitrix API error {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()

    @classmethod
    async def refresh_tokens(
        cls,
        domain: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"https://{domain}/oauth/token/", data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            })
            resp.raise_for_status()
            data = resp.json()
        if not data.get("access_token"):
            raise ValueError(f"Token refresh failed: {data}")
        return data

    async def send_message_to_deal_chat(
            self,
            deal_id: str,
            message: dict,
    ) -> dict:
        return await self.call(
            "imconnector.send.messages",
            message,
            use_json=True,
        )

    async def send_message(
            self,
            connector_id: str,
            line_id: str,
            user_id: str,
            user_name: str,
            chat_id: str,
            text: str,
            message_id: str | None = None,
            media: list[dict] = [],
            deal_id: int | None = None,
            crm_chat_id: str | None = None,
    ) -> dict:
        msg_id = message_id or str(uuid.uuid4())
        log.warning(f"SEND_MESSAGE CALLED msg_id={msg_id} text={text}")
        log.warning(
            f"SEND_MESSAGE ENTER msg_id={msg_id} crm_chat_id={crm_chat_id} deal_id={deal_id}"
        )
        log.info(
            f"imconnector.send.messages user_id={user_id} chat_id={chat_id} connector={connector_id} line={line_id}")
        log.warning(f"send_message connector={connector_id} line={line_id} token={self.access_token}")

        msg = {
            "id": msg_id,
            "date": int(datetime.now(timezone.utc).timestamp()),
            "text": text or " ",
        }
        if media:
            from services.storage_service import StorageService
            storage = StorageService()
            msg["files"] = [
                {
                    "url": storage.presigned_url(m["id"]),
                    "name": m["file_name"],
                }
                for m in media
            ]

        contact_id = await self.find_contact_by_phone(user_id)
        deal_id = await self.find_open_deal(contact_id)

        params = {
            "CONNECTOR": connector_id,
            "LINE": line_id,
            "MESSAGES": [
                {
                    "user": {
                        "id": user_id,
                        "name": user_name,
                        "phone": user_id,
                        "skip_phone_validate": "Y",
                    },
                    "message": msg,
                    "chat": {
                        "id": chat_id,
                        "name": f"Диалог {user_id}",
                        "crm_entity_type": "deal",
                        "crm_entity_id": str(deal_id) if deal_id else None,
                    },
                }
            ],
        }

        if crm_chat_id and deal_id:
            check = await self.call(
                "imopenlines.crm.chat.get",
                {"CRM_ENTITY_TYPE": "deal", "CRM_ENTITY": deal_id or 0, "ACTIVE_ONLY": "N"},
            )
            active_chat = next(
                (c for c in check.get("result", []) if str(c.get("CHAT_ID")) == str(crm_chat_id)),
                None,
            )
            if active_chat:
                result = await self.call(
                    "imconnector.send.messages",
                    params,
                    use_json=True,
                )
                log.warning(f"IMCONNECTOR RESULT {result}")

                real_message_id = None
                try:
                    dlg = await self.call("im.dialog.messages.get", {"DIALOG_ID": f"chat{crm_chat_id}", "LIMIT": 1})
                    log.info(f"\n\n ---- send_message dialog messages result: {dlg} \n\n")
                    msgs = dlg.get("result", {}).get("messages", [])
                    if msgs:
                        real_message_id = msgs[0].get("id")
                except Exception as e:
                    log.warning(f"im.dialog.messages.get failed: {e}")

                result["_real_message_id"] = real_message_id

                im = result.get("result", {})
                if isinstance(im, dict) and im.get("chat_id") and im.get("message_id"):
                    await self.call("imconnector.send.status.delivery", {
                        "CONNECTOR": connector_id,
                        "LINE": line_id,
                        "MESSAGES[0][im][chat_id]": str(im["chat_id"]),
                        "MESSAGES[0][im][message_id]": str(im["message_id"]),
                        "MESSAGES[0][message][id][0]": msg_id,
                        "MESSAGES[0][chat][id]": chat_id,
                    })
                return result

        log.info(f"send_message params: {params}")

        if deal_id:
            if deal_id:
                chat = await self.call(
                    "imopenlines.crm.chat.get",
                    {"CRM_ENTITY_TYPE": "deal", "CRM_ENTITY": deal_id},
                )
                current_user = await self.call("user.current", {})
                operator_id = current_user.get("result", {}).get("ID")

                log.info(f"\n\n chat_get result: {chat} \n\n")
                if chat.get("result") and chat["result"][0].get("CONNECTOR_ID") == connector_id:
                    bitrix_chat_id = chat["result"][0]["CHAT_ID"]
                    result = await self.call("imconnector.send.messages", params, use_json=True)
                else:
                    log.info(f"bitrix crm chat lookup result={chat}")
                    result = await self.call("imconnector.send.messages", params, use_json=True)
                    session = result.get("result", {}).get("DATA", {}).get("RESULT", [{}])[0].get("session", {})
                    bitrix_chat_id = session.get("CHAT_ID")
                    log.info(f"new bitrix chat={bitrix_chat_id} for deal={deal_id}")

                real_message_id = None
                if bitrix_chat_id:
                    try:
                        dlg = await self.call("im.dialog.messages.get",
                                              {"DIALOG_ID": f"chat{bitrix_chat_id}", "LIMIT": 1})
                        msgs = dlg.get("result", {}).get("messages", [])
                        if msgs:
                            real_message_id = msgs[0].get("id")
                    except Exception as e:
                        log.warning(f"im.dialog.messages.get failed: {e}")
                result["_real_message_id"] = real_message_id
        else:
            result = await self.call(
                "imconnector.send.messages",
                params,
                use_json=True,
            )

        log.info(f"send_message result: {result}")
        im = result.get("result", {})
        if isinstance(im, dict) and im.get("chat_id") and im.get("message_id"):
            await self.call("imconnector.send.status.delivery", {
                "CONNECTOR": connector_id,
                "LINE": line_id,
                "MESSAGES[0][im][chat_id]": str(im["chat_id"]),
                "MESSAGES[0][im][message_id]": str(im["message_id"]),
                "MESSAGES[0][message][id][0]": msg_id,
                "MESSAGES[0][chat][id]": chat_id,
            })
        return result

    async def update_message(self, connector_id: str, line_id: str, user_id: str, chat_id: str, msg_id: str,
                             text: str) -> dict:
        params = {
            "CONNECTOR": connector_id,
            "LINE": line_id,
            "MESSAGES": [
                {
                    "user": {"id": user_id},
                    "message": {"id": msg_id, "text": text or " "},
                    "chat": {"id": chat_id},
                }
            ],
        }
        return await self.call("imconnector.update.messages", params, use_json=True)


    async def find_contact_by_phone(self, phone: str) -> str | None:
        result = await self.call("crm.contact.list", {
            "filter[PHONE]": phone,
            "select[]": "ID",
        })
        items = result.get("result", [])
        return str(items[0]["ID"]) if items else None

    async def find_open_deal(self, contact_id: str) -> str | None:
        result = await self.call("crm.deal.list", {
            "filter[CONTACT_ID]": contact_id,
            "filter[!STAGE_ID]": ["WON", "LOSE", "APOLOGY"],
            "select[]": "ID",
        })
        items = result.get("result", [])
        return str(items[0]["ID"]) if items else None

    async def attach_deal_to_chat(self, session_id: str, line_id: str, connector_id: str, deal_id: str) -> dict:
        return await self.call("imopenlines.crm.lead.create", {
            "CHAT_ID": session_id,
            "CRM_ENTITY_TYPE": "deal",
            "CRM_ENTITY_ID": deal_id,
        })

    async def get_contact_phone(self, contact_id: str) -> str | None:
        result = await self.call("crm.contact.get", {"ID": contact_id})
        phones = result.get("result", {}).get("PHONE", [])
        return phones[0].get("VALUE") if phones else None


    async def send_status_delivery(
        self,
        connector_id: str,
        line_id: str,
        chat_id: str,
        im_chat_id: str,
        im_message_id: str,
        message_id: str,
    ) -> dict:
        return await self.call("imconnector.send.status.delivery", {
            "CONNECTOR": connector_id,
            "LINE": line_id,
            "MESSAGES[0][im][chat_id]": im_chat_id,
            "MESSAGES[0][im][message_id]": im_message_id,
            "MESSAGES[0][message][id][0]": message_id,
            "MESSAGES[0][chat][id]": chat_id,
        })

    async def create_open_line(self, name: str) -> str:
        result = await self.call("imopenlines.config.add", {
            "FIELDS[LINE_NAME]": name,
            "FIELDS[QUEUE_TIME]": 60,
        })
        return str(result["result"])

    async def register_connector(self, connector_id: str, name: str = "DoveChat"):
        return await self.call("imconnector.register", {
            "ID": connector_id,
            "NAME": name,
            "CAN_FIRST_WRITE": "Y",
            "ICON[DATA_IMAGE]": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>",
            "ICON[COLOR]": "#4f46e5",
            "ICON_DISABLED[DATA_IMAGE]": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>",
            "ICON_DISABLED[COLOR]": "#99adb3",
            "PLACEMENT_HANDLER": f"{settings.host_url}/crm/api/v1/install/bitrix",
        })

    async def link_connector(self, open_line_id: str, connector_id: str) -> dict:
        return await self.call("imconnector.connector.data.set", {
            "CONNECTOR": connector_id,
            "LINE": open_line_id,
            "DATA[ID]": f"{connector_id}_line{open_line_id}",
            "DATA[ACTIVE]": "Y",
        })

    async def activate_connector(self, open_line_id, connector_id):
        return await self.call("imconnector.activate", {
            "CONNECTOR": connector_id,
            "LINE": open_line_id,
            "ACTIVE": "1",
        })

    async def delete_message(
            self,
            connector_id: str,
            line_id: str,
            user_id: str,
            message_id: str,
            chat_id: str,
    ) -> dict:
        res = await self.call(
            "imconnector.delete.messages",
            {
                "CONNECTOR": connector_id,
                "LINE": line_id,
                "MESSAGES": [
                    {
                        "user": {"id": user_id},
                        "message": {"id": message_id},
                        "chat": {"id": chat_id},
                    }
                ],
            },
            use_json=True,
        )
        log.info(f"\n\n BitrixClient delete_message res {res} \n\n")

    async def delete_message_im(self, message_id: str) -> dict:
        return await self.call("im.message.delete", {"MESSAGE_ID": message_id}, use_json=True)

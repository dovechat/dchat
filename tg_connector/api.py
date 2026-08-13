import asyncio
import base64
import io
import logging
import sys

import qrcode

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from kafka import start_kafka, stop_kafka
from pool import pool
from schemas import DeleteMessageRequest, EditMessageRequest, PhoneRequest, SendMessageRequest
from core.config import settings
from sender import send_message
from tg_client import TelegramClientWrapper
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s", stream=sys.stdout)
log = logging.getLogger("uvicorn")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_qr_state = {}
_auth_state = {}


@app.on_event("startup")
async def startup():
    await start_kafka()
    await pool.start_all()
    asyncio.create_task(pool.health_check_loop())


@app.on_event("shutdown")
async def shutdown():
    for line_id in list(pool.connections.keys()):
        await pool.stop_channel(line_id)
    await stop_kafka()


# ---- Auth (без изменений контракта) ----

@app.post("/auth/start")
async def start_auth(req: PhoneRequest):
    try:
        client = TelegramClientWrapper(use_mock=False)
        result = await client.start_phone(req.phone)
        _auth_state[req.phone] = {
            "client": client,
            "phone_code_hash": result.phone_code_hash,
            "temporary": True,
        }
        return {"status": "code_sent"}
    except Exception as e:
        log.error(f"ERROR: can't send code /auth/start e {e}")


@app.post("/auth/check")
async def check_code(phone: str, code: str):
    state = _auth_state.get(phone)
    if not state:
        return {"error": "No auth started"}

    state["client"].phone_code_hash = state["phone_code_hash"]
    session = await state["client"].check_code(code, phone, state["phone_code_hash"])
    if state["temporary"]:
        await state["client"].disconnect()
    return {"status": "authorized", "session": session}


async def _wait_for_qr(token: str):
    state = _qr_state.get(token)
    if not state:
        return
    try:
        await state["qr_login"].wait(timeout=120)
        session = state["client"].client.session.save()
        me = await state["client"].client.get_me()
        state["session"] = session
        state["phone"] = me.phone
        state["status"] = "authorized"
    except asyncio.TimeoutError:
        state["status"] = "expired"
    except Exception as e:
        state["status"] = "error"
        log.error(f"QR wait error: {e}")
    finally:
        try:
            await state["client"].disconnect()
        except Exception:
            pass


@app.post("/auth/qr/start")
async def start_qr_auth():
    for token, state in _qr_state.items():
        if state["status"] == "pending":
            return {"error": "QR already pending"}

    client = TelegramClientWrapper(use_mock=False)
    qr_login = await client.start_qr()

    img = qrcode.make(qr_login.url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    token = qr_login.url
    _qr_state[token] = {"client": client, "qr_login": qr_login, "status": "pending", "temporary": True,}

    asyncio.create_task(_wait_for_qr(token))

    return {"qr": qr_b64, "token": token}


@app.get("/auth/qr/status")
async def check_qr_status(token: str):
    state = _qr_state.get(token)
    if not state:
        return {"status": "not_found"}
    log.info(f"\n\n --- state {state} \n\n")
    return {"status": state["status"], "session": state.get("session"), "phone": state.get("phone")}


@app.post("/prod/check-phone")
async def check_phone(req: PhoneRequest):
    log.info("\n\n ------ /prod/check-phone check_phone start")
    if not req.session_string:
        return {"error": "session_string required"}
    client = TelegramClientWrapper(
        session_string=req.session_string
    )
    log.info(f"\n\n ------ check_phone client {client}")
    try:
        await client.connect()
        result = await client(ImportContactsRequest([
            InputPhoneContact(client_id=0, phone=req.phone, first_name="", last_name="")
        ]))
        exists = len(result.users) > 0
        user_id = result.users[0].id if exists else None
        res = {"exists": exists, "user_id": user_id}
        log.info(f"\n\n ------ check_phone client return res {res}")
        return res
    finally:
        await client.disconnect()
        log.info("\n\n ------ check_phone finish")

# ---- Пул активных telegram_user каналов (новое) ----

@app.get("/status")
async def status():
    return {"channels": pool.status()}


@app.post("/channels/{line_id}/start")
async def start_channel(line_id: str, phone: str = ""):
    result = await pool.start_channel(line_id, phone)
    return {"status": result}


@app.post("/channels/{line_id}/stop")
async def stop_channel(line_id: str):
    await pool.stop_channel(line_id)
    return {"status": "stopped"}


@app.post("/send")
async def send_messages(req: SendMessageRequest):
    log.info(f"\n\n req {req} req")
    client = pool.get_client(req.line_id)
    if not client:
        raise HTTPException(status_code=400, detail=f"can't create client")

    try:
        entity = await client.get_entity(req.phone)

        sent = await send_message(
            client,
            entity,
            req.text,
            req.media,
        )

        return {
            "status": "sent",
            "channel_msg_id": ",".join(str(m.id) for m in sent) if isinstance(sent, list) else str(sent.id),
        }

    except Exception as e:
        log.error(
            f"send_message failed line={req.line_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=502,
            detail=str(e),
        )


@app.post("/edit")
async def edit_message(req: EditMessageRequest):
    client = pool.get_client(req.line_id)
    if not client:
        msg = f"No active connection for line {req.line_id}"
        log.info(f"@app.post / edit msg {msg}")
        raise HTTPException(status_code=409, detail=msg)
    try:
        entity = await client.get_entity(req.phone)
        await client.edit_message(entity, int(req.channel_msg_id), req.text)
        return {"status": "edited"}
    except Exception as e:
        log.error(f"edit_message failed line={req.line_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/delete")
async def delete_message(req: DeleteMessageRequest):
    client = pool.get_client(req.line_id)
    if not client:
        raise HTTPException(status_code=409, detail=f"No active connection for line {req.line_id}")
    try:
        entity = await client.get_entity(req.phone)
        await client.delete_messages(
            entity,
            [int(x) for x in req.channel_msg_id.split(",")],
        )
        return {"status": "deleted"}
    except Exception as e:
        log.error(f"delete_message failed line={req.line_id}: {e}")
        raise HTTPException(status_code=502, detail=str(e))
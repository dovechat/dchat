from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os, base64

b64_key = os.environ["APP_ENCRYPTION_KEY"]
key = base64.b64decode(b64_key)
aes = AESGCM(key)

def encrypt(text: str) -> str:
    data = text.encode("utf-8")
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, data, None)
    return base64.b64encode(nonce + ct).decode()

def decrypt(token: str) -> bytes:
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    return aes.decrypt(nonce, ct, None).decode("utf-8")


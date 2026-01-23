import httpx
from core.config import settings

class SMSSender:
    def __init__(self):
        # FIXED URL: Includes the /devices/ segment required by the API
        self.url = f"https://api.textbee.dev/api/v1/gateway/devices/{settings.device_id}/send-sms/"

    def send(self, to_phone: str, message: str) -> bool:
        headers = {
            "x-api-key": settings.apikey,
            "Content-Type": "application/json"
        }
        payload = {
            "recipients": [to_phone],
            "message": message
        }

        try:
            with httpx.Client() as client:
                response = client.post(self.url, headers=headers, json=payload, timeout=15.0)
                return response.status_code in (200, 201)
        except Exception as e:
            print(f"SMS Gateway Error: {e}")
            return False

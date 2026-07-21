from app.senders.telegram_user import TelegramUserSender
from app.senders.telegram_bot import TelegramBotSender
from app.senders.whatsapp_green import WhatsAppGreenSender
from app.senders.waba import WabaSender
from app.senders.vk import VKSender

class SenderFactory:
    @staticmethod
    def get_sender(channel_type: str):
        if channel_type == "telegram_user":
            return TelegramUserSender()
        elif channel_type == "telegram_bot":
            return TelegramBotSender()
        elif channel_type == "whatsapp_green":
            return WhatsAppGreenSender()
        elif channel_type == "waba":
            return WabaSender()
        elif channel_type == "vk":
            return VKSender()
        else:
            raise ValueError(f"Unknown channel type: {channel_type}")
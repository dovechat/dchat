from app.senders.telegram_user import TelegramUserSender
from app.senders.telegram_bot import TelegramBotSender
from app.senders.whatsapp_green import WhatsAppGreenSender

class SenderFactory:
    @staticmethod
    def get_sender(channel_type: str):
        if channel_type == "telegram_user":
            return TelegramUserSender()
        elif channel_type == "telegram_bot":
            return TelegramBotSender()
        elif channel_type == "whatsapp_green":
            return WhatsAppGreenSender()  # новый класс
        else:
            raise ValueError(f"Unknown channel type: {channel_type}")
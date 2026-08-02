import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Telegram
    TG_API_ID: int | str = 0
    TG_API_HASH: str = ""
    TG_PHONE: str = ""
    TEST_MODE: bool = False
    
    # Kafka Topics
    TOPIC_INCOMING_MESSAGES: str = "telegram.incoming.messages"
    TOPIC_MESSAGE_STATUS: str = "telegram.message.status"
    TOPIC_CONTACT_SYNC: str = "telegram.contact.sync"

    TG_PROXY_HOST: str = ""
    TG_PROXY_PORT: str = ""
    TG_PROXY_SECRET: str = ""

settings = Settings()
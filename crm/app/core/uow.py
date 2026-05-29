from sqlalchemy.ext.asyncio import AsyncSession
from repo.base import BaseRepository
from models.lines import ChannelAccount, Line
from crm.app.repositories.crm_repo import CrmConnectionRepository, CrmDialogLinkRepository
from repo.crm_settings_repo import CrmSettingsRepository
from models.crm import CrmSettings
from models.messages import Conversation


class CrmUnitOfWork:
    def __init__(self, db: AsyncSession):
        self.crm_connections = CrmConnectionRepository(db)
        self.crm_dialog_links = CrmDialogLinkRepository(db)
        self.crm_settings = CrmSettingsRepository(db)
        self.channel_accounts = BaseRepository(ChannelAccount, db)
        self.lines = BaseRepository(Line, db)
        self.conversations = BaseRepository(Conversation, db)
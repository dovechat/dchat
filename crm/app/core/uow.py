from sqlalchemy.ext.asyncio import AsyncSession
from repo.base import BaseRepository
from models.lines import ChannelAccount, Line
from models.crm import CrmAccount
from crm.app.repositories.crm_repo import CrmAccountRepository, CrmDialogLinkRepository
from repo.crm_repo import CrmLineConnectionRepository
from repo.crm_repo import CrmSettingsRepository
from models.crm import CrmSettings
from models.messages import Conversation
from models.tenants import Membership, User


class CrmUnitOfWork:
    def __init__(self, db: AsyncSession):
        self.crm_accounts = CrmAccountRepository(db)
        self.crm_dialog_links = CrmDialogLinkRepository(db)
        self.crm_settings = CrmSettingsRepository(db)
        self.crm_line_connections = CrmLineConnectionRepository(db)
        self.channel_accounts = BaseRepository(ChannelAccount, db)
        self.lines = BaseRepository(Line, db)
        self.conversations = BaseRepository(Conversation, db)
        self.memberships = BaseRepository(Membership, db)
        self.users = BaseRepository(User, db)

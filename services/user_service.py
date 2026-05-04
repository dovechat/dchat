from core.security import get_password_hash
from repo.user import UserRepository
from services.jwt_services import JWTService

class UserService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo
        self.jwt_service = JWTService()

    async def get_me(self, user_id):
        return await self.user_repo.get_by_id(user_id)

    async def update_me(self, user_id, full_name: str | None, phone: str | None):
        user = await self.user_repo.get_by_id(user_id)
        return await self.user_repo.update(user, full_name=full_name, phone=phone)

    async def change_password(self, user_id, password: str, password_confirm: str):
        if password != password_confirm:
            raise ValueError("Пароли не совпадают")
        user = await self.user_repo.get_by_id(user_id)
        hashed = self.jwt_service.password_hash(password)
        return await self.user_repo.update(user, password_hash=hashed)
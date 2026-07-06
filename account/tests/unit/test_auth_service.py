import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from services.auth_service import AuthService


@pytest.mark.asyncio
async def test_switch_context_success():
    jwt_service = MagicMock()
    jwt_service.create_token_pair.return_value = {"access_token": "ok", "refresh_token": "tok"}
    db = AsyncMock()

    auth_service = AuthService(jwt_service)
    u_id = uuid.uuid4()
    t_id = uuid.uuid4()

    membership = MagicMock(role="admin")

    with patch("services.auth_service.UserRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_membership = AsyncMock(return_value=membership)
        mock_user = MagicMock(role="user")
        mock_repo.get_by_id = AsyncMock(return_value=mock_user)

        result = await auth_service.switch_context(db, u_id, t_id)

        assert result == {"access_token": "ok", "refresh_token": "tok"}
        mock_repo.get_membership.assert_called_once_with(u_id, t_id)


@pytest.mark.asyncio
async def test_switch_context_forbidden():
    jwt_service = MagicMock()
    db = MagicMock()
    auth_service = AuthService(jwt_service)

    with patch("services.auth_service.UserRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_membership = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await auth_service.switch_context(db, uuid.uuid4(), uuid.uuid4())
        assert exc.value.status_code == 403
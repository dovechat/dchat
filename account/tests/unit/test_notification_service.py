import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

from models.notifications import (
    NotificationSettings,
    NotificationLog,
    NotificationType,
    NotificationChannel,
    NotificationStatus,
)
from account.app.services.notification_service import NotificationService


@pytest.fixture
def mock_repo():
    """Mock repository"""
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    """Service instance with mocked repo"""
    return NotificationService(mock_repo, AsyncMock())


@pytest.fixture
def tenant_id():
    return uuid4()


@pytest.fixture
def settings_id():
    return uuid4()


class TestNotificationSettingsCreate:
    """Тесты создания настроек уведомлений"""

    @pytest.mark.asyncio
    async def test_create_settings_success(self, service, mock_repo, tenant_id):
        """Успешное создание настройки"""
        # Arrange
        user_id = uuid4()
        service.membership_repo.get_multi.return_value = [MagicMock(tenant_id=tenant_id)]
        mock_repo.get_settings_by_type_and_channel.return_value = None
        expected_settings = NotificationSettings(
            id=uuid4(),
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            enabled=True,
            created_at=datetime.now(timezone.utc),
        )
        mock_repo.create_settings.return_value = expected_settings

        # Act
        result = await service.create_settings(
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            enabled=True,
            user_id=user_id,
        )

        # Assert
        assert result == [expected_settings]
        mock_repo.get_settings_by_type_and_channel.assert_called_once_with(
            tenant_id, NotificationType.line_expiration, NotificationChannel.email
        )
        mock_repo.create_settings.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_settings_duplicate(self, service, mock_repo, tenant_id):
        """Попытка создать дубликат настройки"""
        # Arrange
        existing_settings = NotificationSettings(
            id=uuid4(),
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            enabled=True,
        )
        mock_repo.get_settings_by_type_and_channel.return_value = existing_settings

        service.membership_repo.get_multi.return_value = [MagicMock(tenant_id=tenant_id)]

        # Act & Assert
        with pytest.raises(ValueError, match="already exist"):
            await service.create_settings(
                tenant_id=tenant_id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                user_id=uuid4()
            )

        mock_repo.create_settings.assert_not_called()


class TestNotificationSettingsRead:
    """Тесты чтения настроек уведомлений"""

    @pytest.mark.asyncio
    async def test_get_all_settings(self, service, mock_repo, tenant_id):
        """Получение всех настроек тенанта"""
        # Arrange
        settings_list = [
            NotificationSettings(
                id=uuid4(),
                tenant_id=tenant_id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                enabled=True,
            ),
            NotificationSettings(
                id=uuid4(),
                tenant_id=tenant_id,
                notification_type=NotificationType.low_balance,
                channel=NotificationChannel.telegram,
                target="@testuser",
                enabled=False,
            ),
        ]
        mock_repo.get_all_settings.return_value = settings_list

        # Act
        result = await service.get_all_settings(tenant_id)

        # Assert
        assert result == settings_list
        assert len(result) == 2
        mock_repo.get_all_settings.assert_called_once_with(tenant_id)

    @pytest.mark.asyncio
    async def test_get_settings_by_id_found(self, service, mock_repo, tenant_id, settings_id):
        """Получение настройки по ID - найдена"""
        # Arrange
        expected_settings = NotificationSettings(
            id=settings_id,
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            enabled=True,
        )
        mock_repo.get_settings_by_id.return_value = expected_settings

        # Act
        result = await service.get_settings_by_id(settings_id, tenant_id)

        # Assert
        assert result == expected_settings
        mock_repo.get_settings_by_id.assert_called_once_with(settings_id, tenant_id)

    @pytest.mark.asyncio
    async def test_get_settings_by_id_not_found(self, service, mock_repo, tenant_id, settings_id):
        """Получение настройки по ID - не найдена"""
        # Arrange
        mock_repo.get_settings_by_id.return_value = None

        # Act
        result = await service.get_settings_by_id(settings_id, tenant_id)

        # Assert
        assert result is None


class TestNotificationSettingsUpdate:
    """Тесты обновления настроек уведомлений"""

    @pytest.mark.asyncio
    async def test_update_settings_success(self, service, mock_repo, tenant_id, settings_id):
        """Успешное обновление настройки"""
        # Arrange
        existing_settings = NotificationSettings(
            id=settings_id,
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="old@example.com",
            enabled=True,
        )
        updated_settings = NotificationSettings(
            id=settings_id,
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="new@example.com",
            enabled=False,
        )
        mock_repo.get_settings_by_id.return_value = existing_settings
        mock_repo.update_settings.return_value = updated_settings

        # Act
        result = await service.update_settings(
            settings_id=settings_id,
            tenant_id=tenant_id,
            enabled=False,
            target="new@example.com",
        )

        # Assert
        assert result == updated_settings
        mock_repo.update_settings.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_settings_not_found(self, service, mock_repo, tenant_id, settings_id):
        """Попытка обновить несуществующую настройку"""
        # Arrange
        mock_repo.get_settings_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await service.update_settings(
                settings_id=settings_id,
                tenant_id=tenant_id,
                enabled=False,
            )

        mock_repo.update_settings.assert_not_called()


class TestNotificationSettingsDelete:
    """Тесты удаления настроек уведомлений"""

    @pytest.mark.asyncio
    async def test_delete_settings_success(self, service, mock_repo, tenant_id, settings_id):
        """Успешное удаление настройки"""
        # Arrange
        existing_settings = NotificationSettings(
            id=settings_id,
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            enabled=True,
        )
        mock_repo.get_settings_by_id.return_value = existing_settings

        service.membership_repo.get_multi.return_value = [MagicMock(tenant_id=tenant_id)]
        mock_repo.get_settings_by_type_and_channel.return_value = existing_settings

        # Act
        await service.delete_settings(settings_id, tenant_id, user_id=uuid4())

        # Assert
        mock_repo.delete_settings.assert_called_once_with(existing_settings)

    @pytest.mark.asyncio
    async def test_delete_settings_not_found(self, service, mock_repo, tenant_id, settings_id):
        """Попытка удалить несуществующую настройку"""
        # Arrange
        mock_repo.get_settings_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await service.delete_settings(settings_id, tenant_id, user_id=uuid4())

        mock_repo.delete_settings.assert_not_called()


class TestNotificationHistory:
    """Тесты истории уведомлений"""

    @pytest.mark.asyncio
    async def test_get_notification_history(self, service, mock_repo, tenant_id):
        """Получение истории уведомлений"""
        # Arrange
        logs = [
            NotificationLog(
                id=1,
                tenant_id=tenant_id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                message="Your line expires soon",
                status=NotificationStatus.sent,
                sent_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            ),
        ]
        mock_repo.get_logs.return_value = logs

        # Act
        result = await service.get_notification_history(
            tenant_id=tenant_id,
            limit=50,
            offset=0,
        )

        # Assert
        assert result == logs
        mock_repo.get_logs.assert_called_once_with(tenant_id, 50, 0, None)


class TestSendNotification:
    """Тесты отправки уведомлений (заглушка)"""

    @pytest.mark.asyncio
    async def test_send_notification_success(self, service, mock_repo, tenant_id):
        """Успешная 'отправка' уведомления"""
        # Arrange
        settings_list = [
            NotificationSettings(
                id=uuid4(),
                tenant_id=tenant_id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                enabled=True,
            ),
        ]
        mock_repo.get_enabled_settings_by_type.return_value = settings_list

        log = NotificationLog(
            id=1,
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            channel=NotificationChannel.email,
            target="test@example.com",
            message="Test message",
            status=NotificationStatus.sent,
            sent_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        mock_repo.create_log.return_value = log

        # Act
        result = await service.send_notification(
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            message="Test message",
        )

        # Assert
        assert len(result) == 1
        assert result[0] == log
        mock_repo.get_enabled_settings_by_type.assert_called_once()
        mock_repo.create_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_notification_no_settings(self, service, mock_repo, tenant_id):
        """Попытка отправить уведомление без настроек"""
        # Arrange
        mock_repo.get_enabled_settings_by_type.return_value = []

        # Act
        result = await service.send_notification(
            tenant_id=tenant_id,
            notification_type=NotificationType.line_expiration,
            message="Test message",
        )

        # Assert
        assert result == []
        mock_repo.create_log.assert_not_called()
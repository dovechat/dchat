import pytest
from httpx import AsyncClient
from uuid import uuid4
from sqlalchemy import select

from tests.conftest import get_test_db
from models.notifications import (
    NotificationSettings,
    NotificationType,
    NotificationChannel,
)


class TestNotificationSettingsAPI:
    """Интеграционные тесты API настроек уведомлений"""

    @pytest.mark.asyncio
    async def test_create_settings_success(
        self, 
        client, 
        token_with_tenant, 
        test_tenant
    ):
        """Создание настройки уведомлений"""
        # Arrange
        payload = {
            "notification_type": "line_expiration",
            "channel": "email",
            "target": "test@example.com",
            "enabled": True,
        }

        # Act
        response = await client.post(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["notification_type"] == "line_expiration"
        assert data["channel"] == "email"
        assert data["target"] == "test@example.com"
        assert data["enabled"] is True
        assert data["tenant_id"] == str(test_tenant.id)
        assert "id" in data
        assert "created_at" in data


    @pytest.mark.asyncio
    async def test_create_settings_duplicate(
        self, 
        client, 
        token_with_tenant,
        test_tenant
    ):
        """Попытка создать дубликат настройки"""
        # Arrange - создаем первую настройку в БД
        async with get_test_db() as session:
            existing = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                enabled=True,
            )
            session.add(existing)
            await session.commit()

        payload = {
            "notification_type": "line_expiration",
            "channel": "email",
            "target": "another@example.com",
            "enabled": True,
        }

        # Act
        response = await client.post(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 400
        assert "already exist" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_all_settings(
        self, 
        client, 
        token_with_tenant,
        test_tenant
    ):
        """Получение всех настроек тенанта"""
        # Arrange - создаем несколько настроек в БД
        async with get_test_db() as session:
            settings1 = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test1@example.com",
                enabled=True,
            )
            settings2 = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.low_balance,
                channel=NotificationChannel.telegram,
                target="@testuser",
                enabled=False,
            )
            session.add_all([settings1, settings2])
            await session.commit()

        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(s["notification_type"] == "line_expiration" for s in data)
        assert any(s["notification_type"] == "low_balance" for s in data)

    @pytest.mark.asyncio
    async def test_create_settings_invalid_email(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Валидация email"""
        # Arrange
        payload = {
            "notification_type": "line_expiration",
            "channel": "email",
            "target": "invalid-email",
            "enabled": True,
        }

        # Act
        response = await client.post(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_settings_invalid_telegram(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Валидация telegram chat_id"""
        # Arrange
        payload = {
            "notification_type": "line_expiration",
            "channel": "telegram",
            "target": "invalid_chat_id",
            "enabled": True,
        }

        # Act
        response = await client.post(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_settings_invalid_phone(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Валидация телефона"""
        # Arrange
        payload = {
            "notification_type": "line_expiration",
            "channel": "sms",
            "target": "123",
            "enabled": True,
        }

        # Act
        response = await client.post(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_settings_by_id(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение конкретной настройки по ID"""
        # Arrange
        async with get_test_db() as session:
            settings = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                enabled=True,
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            settings_id = settings.id

        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{settings_id}",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(settings_id)
        assert data["notification_type"] == "line_expiration"

    @pytest.mark.asyncio
    async def test_get_settings_by_id_not_found(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение несуществующей настройки"""
        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{uuid4()}",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_settings(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Обновление настройки"""
        # Arrange
        async with get_test_db() as session:
            settings = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="old@example.com",
                enabled=True,
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            settings_id = settings.id

        payload = {
            "enabled": False,
            "target": "new@example.com",
        }

        # Act
        response = await client.patch(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{settings_id}",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["target"] == "new@example.com"

        # Verify in DB
        async with get_test_db() as session:
            stmt = select(NotificationSettings).where(NotificationSettings.id == settings_id)
            result = await session.execute(stmt)
            updated = result.scalar_one_or_none()
            assert updated.enabled is False
            assert updated.target == "new@example.com"

    @pytest.mark.asyncio
    async def test_update_settings_not_found(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Обновление несуществующей настройки"""
        # Arrange
        payload = {"enabled": False}

        # Act
        response = await client.patch(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{uuid4()}",
            json=payload,
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_settings(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Удаление настройки"""
        # Arrange
        async with get_test_db() as session:
            settings = NotificationSettings(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                enabled=True,
            )
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
            settings_id = settings.id

        # Act
        response = await client.delete(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{settings_id}",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 204

        # Verify deletion in DB
        async with get_test_db() as session:
            stmt = select(NotificationSettings).where(NotificationSettings.id == settings_id)
            result = await session.execute(stmt)
            deleted = result.scalar_one_or_none()
            assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_settings_not_found(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Удаление несуществующей настройки"""
        # Act
        response = await client.delete(
            f"/api/v1/tenants/{test_tenant.id}/notifications/settings/{uuid4()}",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 404


class TestNotificationHistoryAPI:
    """Интеграционные тесты API истории уведомлений"""

    @pytest.mark.asyncio
    async def test_get_notification_history(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение истории уведомлений"""
        # Arrange - создаем несколько логов
        async with get_test_db() as session:
            from models.notifications import NotificationLog
            log1 = NotificationLog(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                message="Line expires soon",
                status="sent",
            )
            log2 = NotificationLog(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.low_balance,
                channel=NotificationChannel.telegram,
                target="@testuser",
                message="Low balance warning",
                status="sent",
            )
            session.add_all([log1, log2])
            await session.commit()

        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/history",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert any(log["notification_type"] == "line_expiration" for log in data)
        assert any(log["notification_type"] == "low_balance" for log in data)

    @pytest.mark.asyncio
    async def test_get_notification_history_with_filter(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение истории с фильтром по типу"""
        # Arrange
        async with get_test_db() as session:
            from models.notifications import NotificationLog
            log1 = NotificationLog(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.line_expiration,
                channel=NotificationChannel.email,
                target="test@example.com",
                message="Line expires soon",
                status="sent",
            )
            log2 = NotificationLog(
                tenant_id=test_tenant.id,
                notification_type=NotificationType.low_balance,
                channel=NotificationChannel.telegram,
                target="@testuser",
                message="Low balance warning",
                status="sent",
            )
            session.add_all([log1, log2])
            await session.commit()

        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/history?notification_type=line_expiration",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["notification_type"] == "line_expiration"

    @pytest.mark.asyncio
    async def test_get_notification_history_with_pagination(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение истории с пагинацией"""
        # Arrange - создаем 5 логов
        async with get_test_db() as session:
            from models.notifications import NotificationLog
            logs = [
                NotificationLog(
                    tenant_id=test_tenant.id,
                    notification_type=NotificationType.line_expiration,
                    channel=NotificationChannel.email,
                    target=f"test{i}@example.com",
                    message=f"Message {i}",
                    status="sent",
                )
                for i in range(5)
            ]
            session.add_all(logs)
            await session.commit()

        # Act - получаем первые 2
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/history?limit=2&offset=0",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Act - получаем следующие 2
        response2 = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/history?limit=2&offset=2",
            headers=token_with_tenant,
        )

        # Assert
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2) == 2

        # Проверяем что это разные записи
        ids1 = {log["id"] for log in data}
        ids2 = {log["id"] for log in data2}
        assert ids1.isdisjoint(ids2)

    @pytest.mark.asyncio
    async def test_get_notification_history_empty(
            self,
            client,
            token_with_tenant,
            test_tenant
    ):
        """Получение истории когда нет уведомлений"""
        # Act
        response = await client.get(
            f"/api/v1/tenants/{test_tenant.id}/notifications/history",
            headers=token_with_tenant,
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0
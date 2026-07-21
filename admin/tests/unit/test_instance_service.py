"""Unit tests for AdminInstanceService."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.instance_service import AdminInstanceService
from app.schemas.admin_schemas import CreateInstanceRequest, BulkCleanRequest
from models.lines import InstanceStatus


def make_uow(*, instance=None, instances=None, existing=None, idle_count=0, allocated_count=0, channels=None):
    uow = MagicMock()
    uow.commit = AsyncMock()

    uow.instances.get_instance = AsyncMock(return_value=instance)
    uow.instances.get_all = AsyncMock(return_value=instances or [])
    uow.instances.get_multi = AsyncMock(return_value=existing or [])
    uow.instances.count = AsyncMock(return_value=len(instances or []))
    uow.instances.count_by_status = AsyncMock(side_effect=lambda s: {
        "idle": idle_count,
        "allocated": allocated_count,
    }.get(s, 0))
    uow.instances.create_instance = AsyncMock(side_effect=lambda provider, external_id, token=None: make_instance(
        provider=provider, external_id=external_id
    ))
    uow.instances.release = AsyncMock(side_effect=lambda i: setattr(i, "status", "idle") or i)
    uow.instances.delete = AsyncMock()

    uow.audit.log = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = channels or []
    uow._session = MagicMock()
    uow._session.execute = AsyncMock(return_value=mock_result)

    return uow


def make_instance(**kwargs):
    inst = MagicMock()
    inst.id = kwargs.get("id", uuid4())
    inst.provider = kwargs.get("provider", "green")
    inst.external_id = kwargs.get("external_id", f"ext-{uuid4()}")
    inst.status = kwargs.get("status", "idle")
    inst.allocated_to_line_id = kwargs.get("allocated_to_line_id", None)
    inst.last_cleanup_at = None
    inst.health = None
    inst.line_name = kwargs.get("line_name", None)

    return inst


class TestListInstances:

    async def test_returns_instances_with_counts(self):
        instances = [make_instance(), make_instance()]
        uow = make_uow(instances=instances, idle_count=1, allocated_count=1)
        service = AdminInstanceService(uow)

        result = await service.list_instances(
            skip=0, limit=100,
            provider=None, status=None,
            actor_id=uuid4(),
        )

        assert len(result.items) == 2
        assert result.idle_count == 1
        assert result.allocated_count == 1


class TestCreateInstance:

    async def test_creates_new_instance(self):
        uow = make_uow(existing=[])
        service = AdminInstanceService(uow)

        result = await service.create_instance(
            CreateInstanceRequest(provider="green", external_id="ext-123", token="test-token"),
            actor_id=uuid4(),
        )

        uow.instances.create_instance.assert_called_once_with(
            provider="green", external_id="ext-123", token=uow.instances.create_instance.call_args.kwargs["token"]
        )

    async def test_raises_409_if_duplicate_external_id(self):
        uow = make_uow(existing=[make_instance()])
        service = AdminInstanceService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_instance(
                CreateInstanceRequest(provider="green", external_id="ext-dupe", token="test-token"),
                actor_id=uuid4(),
            )

        assert exc_info.value.status_code == 409


class TestCleanInstance:

    async def test_releases_instance(self):
        line_id = uuid4()
        inst = make_instance(status="allocated", allocated_to_line_id=line_id)
        uow = make_uow(instance=inst)
        service = AdminInstanceService(uow)

        result = await service.clean_instance(inst.id, actor_id=uuid4())

        uow.instances.release.assert_called_once_with(inst)
        assert "cleaned" in result.message.lower()

    async def test_raises_404_when_not_found(self):
        uow = make_uow(instance=None)
        service = AdminInstanceService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.clean_instance(uuid4(), actor_id=uuid4())

        assert exc_info.value.status_code == 404

    async def test_audit_contains_old_line_id(self):
        line_id = uuid4()
        inst = make_instance(allocated_to_line_id=line_id)
        uow = make_uow(instance=inst)
        service = AdminInstanceService(uow)

        await service.clean_instance(inst.id, actor_id=uuid4())

        details = uow.audit.log.call_args.kwargs["details"]
        assert details["was_allocated_to"] == str(line_id)


class TestBulkClean:

    async def test_cleans_all_found(self):
        inst1 = make_instance()
        inst2 = make_instance()
        uow = make_uow()

        # get_instance возвращает разные инстансы по очереди
        uow.instances.get_instance = AsyncMock(side_effect=[inst1, inst2])
        service = AdminInstanceService(uow)

        result = await service.bulk_clean(
            BulkCleanRequest(instance_ids=[inst1.id, inst2.id]),
            actor_id=uuid4(),
        )

        assert uow.instances.release.call_count == 2
        assert "2" in result.message

    async def test_reports_not_found_ids(self):
        inst = make_instance()
        missing_id = uuid4()
        uow = make_uow()
        uow.instances.get_instance = AsyncMock(side_effect=[inst, None])
        service = AdminInstanceService(uow)

        result = await service.bulk_clean(
            BulkCleanRequest(instance_ids=[inst.id, missing_id]),
            actor_id=uuid4(),
        )

        assert str(missing_id) in result.message
        assert uow.instances.release.call_count == 1


class TestDeleteInstance:

    async def test_deletes_idle_instance(self):
        inst = make_instance(status="idle")
        uow = make_uow(instance=inst)
        service = AdminInstanceService(uow)

        await service.delete_instance(inst.id, actor_id=uuid4())

        uow.instances.delete.assert_called_once_with(inst)

    async def test_raises_409_for_allocated(self):
        inst = make_instance(status=InstanceStatus.busy)
        uow = make_uow(instance=inst)
        service = AdminInstanceService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_instance(inst.id, actor_id=uuid4())

        assert exc_info.value.status_code == 409

    async def test_raises_404_when_not_found(self):
        uow = make_uow(instance=None)
        service = AdminInstanceService(uow)

        with pytest.raises(HTTPException) as exc_info:
            await service.delete_instance(uuid4(), actor_id=uuid4())

        assert exc_info.value.status_code == 404
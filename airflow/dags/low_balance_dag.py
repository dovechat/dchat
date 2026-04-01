import asyncio
import os
from datetime import datetime

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from core.config import settings
from models.tenants import Tenant  # noqa: F401
from models.notifications import NotificationSettings  # noqa: F401
from models.lines import Line  # noqa: F401


def _parse_warn_days() -> list[int]:
    raw = os.getenv("LOW_BALANCE_WARN_DAYS", "5,3")
    raw = settings.low_balance_warn_days
    return [int(d.strip()) for d in raw.split(",") if d.strip().isdigit()]


def check_low_balance(**context):
    async def _run():
        from core.database import AsyncSessionLocal
        from repo.billing_repo import (
            BalanceRepository,
            BalanceLedgerRepository,
            TariffRepository,
        )
        from repo.line_repo import LineRepository
        from notification.notification_repo import (
            NotificationSettingsRepository,
            NotificationLogRepository,
        )
        from services.billing_service import BillingService
        from notification.notification_service import NotificationService

        # warn_days = _parse_warn_days()
        warn_days = settings.low_balance_warn_days

        async with AsyncSessionLocal() as session:
            billing_service = BillingService(
                line_repo=LineRepository(session),
                balance_repo=BalanceRepository(session),
                ledger_repo=BalanceLedgerRepository(session),
                tariff_repo=TariffRepository(session),
            )
            notification_service = NotificationService(
                settings_repo=NotificationSettingsRepository(session),
                log_repo=NotificationLogRepository(session),
            )

            targets = await billing_service.get_low_balance_tenants(warn_days)

            for t in targets:
                await notification_service.notify_low_balance(
                    tenant_id=t["tenant_id"],
                    balance=t["balance"],
                    days_left=t["days_left"],
                )

            print(
                f"\n\n ------------  [low_balance_check] date={context['logical_date']}"
                f"\n\n warn_days={warn_days} notified={len(targets)} \n\n ------------ \n\n"
            )

    asyncio.run(_run())


with DAG(
    dag_id="low_balance_check",
    schedule="0 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["billing", "notifications"],
) as dag:
    PythonOperator(
        task_id="check_low_balance",
        python_callable=check_low_balance,
    )
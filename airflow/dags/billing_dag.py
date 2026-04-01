"""Billing DAG — daily charge for active lines."""
import asyncio
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from core.database import AsyncSessionLocal
from repo.billing_repo import BalanceRepository, BalanceLedgerRepository, TariffRepository
from repo.line_repo import LineRepository
from notification.notification_repo import NotificationSettingsRepository, NotificationLogRepository
from services.billing_service import BillingService
from notification.notification_service import NotificationService
from models.tenants import Tenant  # noqa: F401
from models.notifications import NotificationSettings  # noqa: F401
import logging
log = logging.getLogger("airflow.task")
DEFAULT_ARGS = {
    "owner": "dovechat",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}
async def _charge_lines(period: datetime) -> None:
    async with AsyncSessionLocal() as session:
        try:
            service = BillingService(
                line_repo=LineRepository(session),
                balance_repo=BalanceRepository(session),
                ledger_repo=BalanceLedgerRepository(session),
                tariff_repo=TariffRepository(session),
            )
            notification_service = NotificationService(
                settings_repo=NotificationSettingsRepository(session),
                log_repo=NotificationLogRepository(session),
            )
            results = await service.charge_lines(period.date())
            for line in results["blocked_lines"]:
                await notification_service.notify_line_blocked(
                    tenant_id=line.tenant_id,
                    line_name=line.name,
                )
            await session.commit()
            log.info(f"Billing results for {period.date()}: {results}")
        except Exception:
            await session.rollback()
            raise
def charge_lines_task(**context) -> None:
    execution_date: datetime = context["logical_date"]
    log.info(f"Starting billing for period {execution_date.date()}")
    asyncio.run(_charge_lines(execution_date))
with DAG(
    dag_id="billing_daily_charge",
    description="Daily charge for active lines according to tariff",
    schedule="0 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["billing", "dovechat"],
) as dag:
    charge = PythonOperator(
        task_id="charge_active_lines",
        python_callable=charge_lines_task,
    )
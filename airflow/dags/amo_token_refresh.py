"""Amo token refresh DAG — every 8 hours."""
import asyncio
from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from core.database import AsyncSessionLocal
from infra.crypto import encrypt, decrypt
from crm.app.services.providers.amocrm.client import AmoCrmClient
from core.config import settings
import logging

log = logging.getLogger("airflow.task")

DEFAULT_ARGS = {
    "owner": "dovechat",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
}


async def _refresh_amo_tokens() -> None:
    from models.crm import CrmConnection
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(CrmConnection).where(
                    CrmConnection.crm_type == "amocrm",
                    CrmConnection.is_active.is_(True),
                )
            )
            connections = result.scalars().all()
            log.info(f"amo_token_refresh: found {len(connections)} connections")

            for conn in connections:
                try:
                    tokens = await AmoCrmClient.refresh_tokens(
                        domain=conn.domain,
                        refresh_token=decrypt(conn.refresh_token_enc),
                        client_id=settings.AMO_CLIENT_ID,
                        client_secret=settings.AMO_CLIENT_SECRET,
                        redirect_uri=settings.AMO_REDIRECT_URI,
                    )
                    conn.access_token_enc = encrypt(tokens["access_token"])
                    conn.refresh_token_enc = encrypt(tokens["refresh_token"])
                    log.info(f"amo_token_refresh: refreshed domain={conn.domain}")
                except Exception as e:
                    log.error(f"amo_token_refresh: failed domain={conn.domain} error={e}")

            await session.commit()
        except Exception:
            await session.rollback()
            raise


def refresh_amo_tokens_task(**context):
    asyncio.run(_refresh_amo_tokens())


with DAG(
    dag_id="amo_token_refresh",
    description="Refresh amoCRM OAuth tokens every 8 hours",
    schedule="0 */8 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["crm", "amocrm", "dovechat"],
) as dag:
    refresh = PythonOperator(
        task_id="refresh_amo_tokens",
        python_callable=refresh_amo_tokens_task,
    )
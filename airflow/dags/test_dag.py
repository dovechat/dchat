import asyncio
import asyncpg
import os
from datetime import datetime
from pathlib import Path
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


def get_postgres_config():
    port = os.environ.get("POSTGRES_PORT") or 5432
    if isinstance(port, str) and "tcp://" in port:
        port = port.split(":")[-1]
    port = int(port)
    
    return {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': port,
        'user': os.getenv('POSTGRES_USER'),
        'password': os.getenv('POSTGRES_PASSWORD'),
        'database': os.getenv('POSTGRES_DB'),
    }

async def run_deactivate():
    print("🚀 HELLO WORLD! Airflow работает! 🟢")
    print(f"📁 Dags folder: {os.getenv('AIRFLOW__CORE__DAGS_FOLDER')}")
    print(f"🕐 Время: {datetime.now()}")
    print(f"📊 PID: {os.getpid()}")
    print("✅ Task deactivate_line SUCCESS!")


    conf = get_postgres_config()
    dsn = f"postgresql://{conf['user']}:{conf['password']}@{conf['host']}:{conf['port']}/{conf['database']}"
    conn = await asyncpg.connect(dsn)

    query = """
    SELECT DISTINCT
        l.id as line_id
    FROM lines l
    JOIN channel_accounts ca ON ca.line_id = l.id
    WHERE ca.expires_at - NOW() < INTERVAL '1 day'
    """
    rows = await conn.fetch(query)
    print("rows \n\n")
    print(rows)
    await conn.close()

    return "deactivate_done"


def etl_wrapper(**context):
    print("🎯 PythonOperator wrapper started")
    result = asyncio.run(run_deactivate())
    print(f"🎯 Task result: {result}")
    return result

with DAG(
    dag_id="deactivate",
    start_date=datetime(2026, 3, 20),
    schedule="@hourly",
    catchup=False,
    tags=["test", "hello"],
    max_active_runs=1
) as dag:

    t_etl = PythonOperator(
        task_id="deactivate_line",
        python_callable=etl_wrapper,
        do_xcom_push=True  # сохранит результат в XCom
    )





'''
async def run_extraction():
    conf = get_postgres_config()
    dsn = f"postgresql://{conf['user']}:{conf['password']}@{conf['host']}:{conf['port']}/{conf['database']}"
    conn = await asyncpg.connect(dsn)

    query = """
    SELECT 
        id as line_id,
    FROM lines
    WHERE expires_at - NOW() < INTERVAL '1 day'
    """
    rows = await conn.fetch(query)
    print("rows \n\n")
    print(rows)


    # Simple product extraction
    query = """
    SELECT 
        id as product_id,
        product_name,
        retail_price,
        discounted_price,
        brand,
        "is_FK_Advantage_product" as is_advantage
    FROM products_product
    """
    rows = await conn.fetch(query)
    ch_rows = [
        {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "retail_price": float(r["retail_price"]) if r["retail_price"] is not None else 0.0,
            "discounted_price": float(r["discounted_price"]) if r["discounted_price"] is not None else 0.0,
            "brand": r["brand"] or "Unknown",
            "is_advantage": bool(r["is_advantage"])
        } for r in rows
    ]
    
    if ch_rows:
        insert_rows("products_analytics", ch_rows)
            
    await conn.close()
    return len(ch_rows)
'''


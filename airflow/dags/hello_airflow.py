from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from datetime import datetime

dag = DAG(
    'hello_airflow',
    start_date=datetime(2026, 3, 1),
    schedule='@daily',
    catchup=False
)

BashOperator(
    task_id='hello',
    bash_command='echo "Hello Airflow!"',
    dag=dag
)

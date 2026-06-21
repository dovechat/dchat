import logging
import os
import re
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.providers.standard.operators.bash import BashOperator
from minio import Minio

log = logging.getLogger(__name__)

DUMP_DIR = "/opt/dovechat/dumps"
BUCKET_NAME = "dumps"


def _get_minio_client() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def upload_dump_to_minio(**context) -> None:
    ds = context["ds"]
    file_name = f"dump_{ds}.sql.gz"
    file_path = f"{DUMP_DIR}/{file_name}"

    client = _get_minio_client()
    client.fput_object(BUCKET_NAME, file_name, file_path)
    log.info(f"upload_dump_to_minio uploaded={file_name} bucket={BUCKET_NAME}")
    os.remove(file_path)


def cleanup_old_dumps(**context) -> None:
    client = _get_minio_client()
    today = datetime.strptime(context["ds"], "%Y-%m-%d").date()
    objects = client.list_objects(BUCKET_NAME)

    dumps = []
    for obj in objects:
        match = re.match(r"dump_(\d{4}-\d{2}-\d{2})\.sql\.gz", obj.object_name)
        if match:
            obj_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            dumps.append((obj_date, obj.object_name))

    keep = set()
    week_seen = set()
    month_seen = set()

    for obj_date, name in sorted(dumps, reverse=True):
        age_days = (today - obj_date).days
        if age_days <= 5:
            keep.add(name)
        elif age_days <= 35:
            week_key = obj_date.isocalendar()[:2]
            if week_key not in week_seen:
                week_seen.add(week_key)
                keep.add(name)
        elif age_days <= 150:
            month_key = (obj_date.year, obj_date.month)
            if month_key not in month_seen:
                month_seen.add(month_key)
                keep.add(name)

    for obj_date, name in dumps:
        if name not in keep:
            client.remove_object(BUCKET_NAME, name)
            log.info(f"cleanup_old_dumps removed={name}")

    log.info(f"cleanup_old_dumps kept={len(keep)} total={len(dumps)}")


default_args = {
    "owner": "dovechat",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="db_backup_dag",
    default_args=default_args,
    schedule="0 3 * * *",
    start_date=datetime(2026, 6, 1),
    catchup=False,
    tags=["backup"],
) as dag:

    dump_db = BashOperator(
        task_id="dump_db",
        bash_command=f"pg_dump $DATABASE_URL | gzip > {DUMP_DIR}/dump_{{{{ ds }}}}.sql.gz",
    )

    upload_dump = PythonOperator(
        task_id="upload_dump",
        python_callable=upload_dump_to_minio,
    )

    cleanup_dump = PythonOperator(
        task_id="cleanup_dump",
        python_callable=cleanup_old_dumps,
    )

    dump_db >> upload_dump >> cleanup_dump
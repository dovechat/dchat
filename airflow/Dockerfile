FROM python:3.12-slim

RUN apt-get update && apt-get install -y graphviz

WORKDIR /mono
COPY .env ./
COPY airflow airflow/
COPY core core/
COPY models models/

COPY services services/
COPY repo repo/
COPY notification notification/
COPY infra infra/

WORKDIR /mono/airflow

RUN pip install --no-cache-dir poetry

# ИСПРАВЛЕНИЕ: указываем, что файлы лежат в папке airflow в контексте билда
COPY airflow/pyproject.toml airflow/poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

ENV AIRFLOW_HOME=/mono/airflow
ENV PYTHONPATH=/mono
ENV DOTENV_PATH=/mono/.env
FROM python:3.12-slim

RUN apt-get update && apt-get install -y graphviz

WORKDIR /mono
COPY .env ./
COPY airflow airflow/
COPY core core/
COPY models models/


WORKDIR /mono/airflow

RUN pip install --no-cache-dir poetry

# COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root


ENV AIRFLOW_HOME=/airflow
ENV PYTHONPATH=/airflow
ENV DOTENV_PATH=/.env

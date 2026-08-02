FROM python:3.11-slim

WORKDIR /mono
COPY tg_connector tg_connector/
WORKDIR /mono/tg_connector

RUN pip install --no-cache-dir poetry==2.1.0

# COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi --no-root

# Теперь код
COPY . .

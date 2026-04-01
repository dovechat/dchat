FROM python:3.12-slim

WORKDIR /app

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Poetry
RUN pip install poetry==1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

# Зависимости
COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-root

# Общие модули монорепы (core, models, repo, schemas, services, infra)
COPY ../core /app/core
COPY ../models /app/models
COPY ../repo /app/repo
COPY ../schemas /app/schemas
COPY ../services /app/services
COPY ../infra /app/infra

# Код сервиса
COPY admin/app /app/app

EXPOSE 8072

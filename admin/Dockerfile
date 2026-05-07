FROM python:3.12-slim

WORKDIR /mono

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY core core/
COPY models models/
COPY repo repo/
COPY schemas schemas/
COPY services services/
COPY infra infra/
COPY admin admin/

WORKDIR /mono/admin
RUN pip install --no-cache-dir poetry==1.8.3
ENV POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN poetry install --no-root

EXPOSE 8072
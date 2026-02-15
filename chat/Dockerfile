FROM python:3.12-slim

WORKDIR /mono
COPY core core/
COPY chat chat/
COPY models models/
COPY repo repo/
COPY schemas schemas/
COPY services services/
COPY alembic ./alembic
COPY alembic.ini ./
# COPY .env ./

WORKDIR /mono/chat
RUN apt update && apt-get install -y postgresql-client
RUN pip install --no-cache-dir poetry==1.7.1

# COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false
RUN poetry install --no-interaction --no-ansi --no-root

RUN useradd -m -u 1001 chatuser && chown -R chatuser:chatuser /mono/chat
USER chatuser

EXPOSE 8001

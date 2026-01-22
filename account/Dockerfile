FROM python:3.12-slim

 # change to project name
WORKDIR /mono
COPY core core/
# change to service name
COPY account account/
COPY models models/
COPY repo repo/
COPY schemas schemas/
COPY services services/
COPY alembic ./alembic
COPY alembic.ini ./
COPY .env ./

# change to project/service name
WORKDIR /mono/account

RUN pip install --no-cache-dir poetry==1.7.1

COPY pyproject.toml poetry.lock ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /mono/account
USER appuser

EXPOSE 8000

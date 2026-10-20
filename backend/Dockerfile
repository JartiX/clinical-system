FROM python:3.12-slim

WORKDIR /srv
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic.ini ./
COPY alembic ./alembic

EXPOSE 8000

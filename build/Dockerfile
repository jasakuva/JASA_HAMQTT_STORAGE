FROM docker.io/library/python:3.13-slim

ARG IMAGE_VERSION=dev
ARG IMAGE_REVISION=unknown

LABEL org.opencontainers.image.title="HAMQTT Store" \
      org.opencontainers.image.description="Home Assistant and MQTT data store application services" \
      org.opencontainers.image.source="https://github.com/jasakuva/JASA_HAMQTT_STORAGE" \
      org.opencontainers.image.version="${IMAGE_VERSION}" \
      org.opencontainers.image.revision="${IMAGE_REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml ./
COPY config/python/requirements.txt ./requirements.txt
COPY src ./src
COPY templates ./templates
COPY static ./static
COPY config/alembic.ini ./alembic.ini
COPY migrations ./migrations

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "hamqtt_store.wsgi:app"]

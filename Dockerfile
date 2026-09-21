# syntax=docker/dockerfile:1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --system opspilot \
    && useradd \
        --system \
        --gid opspilot \
        --create-home \
        --home-dir /home/opspilot \
        opspilot

COPY requirements.txt ./requirements.txt

RUN python -m pip install \
        --no-cache-dir \
        --requirement requirements.txt \
    && python -m pip check

COPY --chown=opspilot:opspilot \
    opspilot_api \
    ./opspilot_api

COPY --chown=opspilot:opspilot \
    scripts \
    ./scripts

COPY --chown=opspilot:opspilot \
    sql \
    ./sql

USER opspilot

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "opspilot_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

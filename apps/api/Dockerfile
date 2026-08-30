FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROCESS_ARCHITECT_WORKSPACE_ROOT=/app

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --create-home app

COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
COPY apps/api/src /app/apps/api/src
COPY apps/api/migrations /app/apps/api/migrations
COPY apps/api/alembic.ini /app/apps/api/alembic.ini
COPY apps/api/docker-entrypoint.sh /app/apps/api/docker-entrypoint.sh
COPY 02_architecture/schemas /app/02_architecture/schemas
COPY config/deployment_profiles /app/config/deployment_profiles
COPY config/entitlements /app/config/entitlements
COPY config/licensing /app/config/licensing
COPY config/llm-pricing /app/config/llm-pricing
COPY data/process_library/n8n/v1 /app/data/process_library/n8n/v1
COPY data/process_library/batch_071_300/v1 /app/data/process_library/batch_071_300/v1

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install /app/apps/api \
    && chmod +x /app/apps/api/docker-entrypoint.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/apps/api/docker-entrypoint.sh"]
CMD ["uvicorn", "process_architect_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

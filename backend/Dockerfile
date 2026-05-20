FROM python:3.11-slim

WORKDIR /app

# System deps for healthy network/SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic
COPY mcp_servers /app/mcp_servers
COPY README.md /app/README.md

WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

RUN mkdir -p /app/data

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=90s \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

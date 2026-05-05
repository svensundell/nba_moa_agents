FROM python:3.11-slim

WORKDIR /app

# System deps for healthy network/SSL
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /app/backend/pyproject.toml
COPY backend/app /app/backend/app
COPY mcp_servers /app/mcp_servers
COPY README.md /app/README.md

WORKDIR /app/backend
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

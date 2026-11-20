#!/usr/bin/env bash
# Build an App Service ZIP for Linux x86_64. Only runtime files enter the archive.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
out=${1:?Pass an absolute output ZIP path}
[[ "$out" = /* && "$out" = *.zip ]] || exit 2
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cd "$repo"
mkdir -p "$stage/backend" "$stage/frontend"
VITE_API_BASE=/api VITE_WS_API_BASE= npm --prefix frontend run build
cp -R backend/app backend/alembic backend/alembic.ini "$stage/backend/"
cp -R mcp_servers "$stage/"
cp -R frontend/dist "$stage/frontend/"
find "$stage" -type d -name __pycache__ -prune -exec rm -rf {} +
uv export --frozen --package nba-moa-agents --no-dev --no-emit-workspace --no-hashes --no-annotate > "$stage/requirements.txt"
docker run --rm --platform linux/amd64 -v "$stage:/release" -w /release python:3.11-slim-bookworm \
    python -m pip install -q --disable-pip-version-check --no-cache-dir --no-compile -r requirements.txt -t packages
cd "$stage"
zip -qr "$stage/site.zip" backend mcp_servers frontend packages requirements.txt
mv "$stage/site.zip" "$out"

#!/usr/bin/env bash
set -euo pipefail

cd backend
python -m alembic upgrade head
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:?Render PORT is not set}" --workers 1

#!/bin/sh
# Railway startup script — reads PORT from environment and passes it to uvicorn
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

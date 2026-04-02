# ShipBridge API — Production Dockerfile
# Used by Fly.io, Render (Docker mode), and any container-based platform.

FROM python:3.11-slim

# Install system dependencies for asyncpg and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port Uvicorn will listen on
EXPOSE 8000

# Health check — used by Railway, Render, and Fly.io
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Default command — override in docker-compose or platform config for workers
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

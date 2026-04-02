# ShipBridge API — Production Dockerfile
# Used by Railway, Fly.io, Render (Docker mode), and any container-based platform.

FROM python:3.11-slim

# Install system dependencies:
#   - gcc / libpq-dev: required by asyncpg and psycopg2
#   - libpango / libcairo / libgdk-pixbuf: required by weasyprint (PDF generation)
#   - libffi-dev / shared-mime-info / fonts-liberation: required by weasyprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    libcairo2 \
    libcairo-gobject2 \
    fonts-liberation \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the default port (Railway overrides this via PORT env var)
EXPOSE 8000

# Health check — used by Railway, Render, and Fly.io
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:' + __import__('os').environ.get('PORT','8000') + '/health')"

# Use Python entrypoint so PORT env var is read via os.environ (not shell expansion)
# Railway injects PORT automatically; entrypoint.py reads it with os.environ.get("PORT", 8000)
CMD ["python", "entrypoint.py"]

# ShipBridge — Backend API

**ShipBridge** is a Pilot-to-Production platform for AI agents. This repository contains the FastAPI backend that powers staged rollouts, HITL governance, cost modelling, connector integrations, and real-time event streaming.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Environment Variables](#environment-variables)
5. [Database Setup](#database-setup)
6. [Running the API](#running-the-api)
7. [Running Tests](#running-tests)
8. [Service Topology](#service-topology)
9. [Connector Credentials](#connector-credentials)
10. [Optional Observability](#optional-observability)
11. [Deployment](#deployment)
12. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    ShipBridge Frontend                  │
│              (React + Vite, port 3000)                  │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────────────┐
│              FastAPI Backend  (port 8000)               │
│  Routers: auth · deployments · rules · costs · events  │
│  Middleware: guardrails (PII) · logging · telemetry     │
└────┬──────────────┬──────────────┬──────────────────────┘
     │              │              │
┌────▼────┐  ┌──────▼──────┐  ┌───▼──────────────────────┐
│Postgres │  │    Redis     │  │   Temporal Workflows     │
│ + pgvec │  │  (Streams)   │  │  (staged rollout logic)  │
└─────────┘  └─────────────┘  └──────────────────────────┘
```

The API is a single **FastAPI** application with async SQLAlchemy for PostgreSQL, Redis for the event stream (Redis Streams), and Temporal for durable workflow orchestration of staged rollouts.

---

## Prerequisites

Before you begin, ensure the following are installed on your machine.

| Tool | Minimum Version | Install |
|---|---|---|
| **Python** | 3.11 | [python.org](https://www.python.org/downloads/) |
| **Docker Desktop** | 4.x | [docker.com](https://www.docker.com/products/docker-desktop/) |
| **Git** | 2.x | [git-scm.com](https://git-scm.com/) |

> **Note:** Docker Desktop is required only for the local infrastructure (Postgres, Redis, Temporal). If you already have these services running elsewhere, you can skip Docker and point the environment variables at your existing instances.

---

## Quick Start

Follow these five steps to go from zero to a running API.

**Step 1 — Clone the repository**

```bash
git clone https://github.com/biswadeepakdas/Shipbridge.git
cd Shipbridge
```

**Step 2 — Start infrastructure services**

```bash
docker compose -f docker-compose.dev.yml up -d
```

This starts PostgreSQL (port `5432`), Redis (port `6379`), Temporal (port `7233`), and the Temporal UI (port `8233`). Wait about 10 seconds for all health checks to pass.

**Step 3 — Create your environment file**

```bash
cp .env.example apps/api/.env
```

Open `apps/api/.env` and fill in at minimum:

```dotenv
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
JWT_SECRET=<any-random-32-char-string>
```

**Step 4 — Install Python dependencies and run migrations**

```bash
cd apps/api
pip install -r requirements.txt
alembic upgrade head
```

**Step 5 — Start the API**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is now live at `http://localhost:8000`. Visit `http://localhost:8000/docs` for the interactive Swagger UI.

---

## Environment Variables

Copy `.env.example` to `apps/api/.env`. The table below documents every variable, its purpose, whether it is required, and where to obtain it.

### Core (Required)

| Variable | Description | Where to get it |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | Defaults to local Docker instance |
| `REDIS_URL` | Redis connection string | Defaults to local Docker instance |
| `JWT_SECRET` | Secret used to sign JWT tokens | Generate with `openssl rand -hex 32` |
| `OPENAI_API_KEY` | Used for embeddings (`text-embedding-3-small`) and LLM routing in the OS layer | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `ANTHROPIC_API_KEY` | Used by the HITL rule-generation worker (Claude) | [console.anthropic.com](https://console.anthropic.com) |

### Temporal (Required if `USE_TEMPORAL=true`)

| Variable | Description | Default |
|---|---|---|
| `TEMPORAL_HOST` | Temporal gRPC address | `localhost:7233` |
| `TEMPORAL_NAMESPACE` | Temporal namespace for ShipBridge workflows | `shipbridge` |
| `USE_TEMPORAL` | Set to `false` to disable Temporal and run rollout logic synchronously | `false` |

> **Tip for local development:** Set `USE_TEMPORAL=false` to skip Temporal entirely. Staged rollout state will be managed in-process without durability guarantees, which is fine for local testing.

### Supabase (Optional)

Supabase is used as an alternative auth and storage backend. If you are running fully locally with plain Postgres, you can leave these blank.

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (server-side only) |

### App Settings

| Variable | Description | Default |
|---|---|---|
| `ENVIRONMENT` | `development`, `staging`, or `production` | `development` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) | `DEBUG` |
| `API_BASE_URL` | Public base URL of this API (used in webhook callbacks) | `http://localhost:8000` |
| `WEB_BASE_URL` | Public base URL of the frontend (used in CORS) | `http://localhost:3000` |

---

## Database Setup

ShipBridge uses **Alembic** for schema migrations. There are currently two migration versions:

1. `330f267d9b26` — Initial migration with all models
2. `de96fdc811ae` — Adds SLA and budget fields

Run all migrations with:

```bash
cd apps/api
alembic upgrade head
```

To seed the database with sample data for local development:

```bash
cd packages/db
python seed.py
```

To reset the database entirely (destructive — local dev only):

```bash
python drop_tables.py
alembic upgrade head
python packages/db/seed.py
```

---

## Running the API

**Development (with hot reload):**

```bash
cd apps/api
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Production:**

```bash
cd apps/api
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Using Make (starts Docker + API + frontend together):**

```bash
make dev
```

### Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check — returns status of DB, Redis, and Temporal |
| `GET /docs` | Interactive Swagger UI |
| `GET /redoc` | ReDoc API documentation |
| `POST /auth/login` | Obtain a JWT token |
| `GET /deployments` | List all agent deployments |
| `POST /deployments/{id}/promote` | Promote a deployment to the next stage |
| `GET /rules` | List HITL rules pending approval |
| `POST /rules/{id}/approve` | Approve a HITL rule |
| `GET /costs` | Aggregated token cost data |
| `GET /governance/audit` | Immutable audit trail |
| `WS /ws/events` | WebSocket stream for live events |

---

## Running Tests

```bash
cd apps/api
python -m pytest -v
```

Run only a specific test module:

```bash
python -m pytest tests/test_deployments.py -v
```

---

## Service Topology

All infrastructure services are defined in `docker-compose.dev.yml` and run on the `shipbridge-network` bridge network.

| Service | Image | Port | Purpose |
|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | `5432` | Primary database with vector extension |
| `redis` | `redis:7-alpine` | `6379` | Event streaming (Redis Streams) and caching |
| `temporal` | `temporalio/auto-setup:latest` | `7233` | Durable workflow orchestration |
| `temporal-ui` | `temporalio/ui:latest` | `8233` | Temporal web dashboard |

**Useful commands:**

```bash
# Start all services
docker compose -f docker-compose.dev.yml up -d

# Check service health
docker compose -f docker-compose.dev.yml ps

# Stop all services
docker compose -f docker-compose.dev.yml down

# Wipe all data volumes (destructive)
docker compose -f docker-compose.dev.yml down -v
```

---

## Connector Credentials

Connectors are optional. The platform degrades gracefully — a connector without credentials will show an "Error" status in the UI but will not crash the API.

| Connector | Variables Required |
|---|---|
| **Salesforce CRM** | `SALESFORCE_USERNAME`, `SALESFORCE_PASSWORD`, `SALESFORCE_SECURITY_TOKEN`, `SALESFORCE_INSTANCE_URL` |
| **Notion** | `NOTION_API_KEY` |
| **Stripe** | `STRIPE_API_KEY` |
| **GitHub App** | `GITHUB_APP_ID`, `GITHUB_WEBHOOK_SECRET`, and a PEM private key file referenced by `GITHUB_PRIVATE_KEY_PATH` |

For Salesforce, generate a security token from **Salesforce → Settings → My Personal Information → Reset My Security Token**.

---

## Optional Observability

### PII Detection (Presidio)

The guardrails middleware uses Microsoft Presidio for PII scanning. It is optional — if not installed, the middleware passes through without scanning and logs a warning.

```bash
pip install presidio-analyzer presidio-anonymizer
python -m spacy download en_core_web_lg
```

### Sentry

Set `SENTRY_DSN` to your project DSN from [sentry.io](https://sentry.io) to enable error tracking.

### OpenTelemetry

Set `OTEL_EXPORTER_OTLP_ENDPOINT` (e.g., `http://localhost:4317`) to export traces to any OTLP-compatible collector (Jaeger, Grafana Tempo, Honeycomb, etc.).

### BetterStack Uptime

Set `BETTERSTACK_HEARTBEAT_URL` to your heartbeat URL to enable uptime monitoring pings.

---

## Deployment

The recommended production deployment path is:

1. Build a Docker image from `apps/api/` using the provided `Dockerfile` (if present) or a standard Python image.
2. Set all environment variables via your hosting provider's secrets manager.
3. Run `alembic upgrade head` as a pre-deploy migration step.
4. Start with `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`.

> **CORS:** In production, update `WEB_BASE_URL` to your frontend's public domain so the CORS middleware allows requests from the correct origin.

---

## Troubleshooting

**`redis_unavailable` warning on startup**
The API starts successfully even without Redis. Check that Docker is running and `docker compose up -d` completed without errors. Verify with `docker compose ps`.

**`alembic.util.exc.CommandError: Can't locate revision`**
Run `alembic stamp head` to mark the current state, then `alembic upgrade head` again.

**`OperationalError: could not connect to server`**
PostgreSQL is not ready. Wait a few seconds after `docker compose up -d` and retry. Check health with `docker compose ps`.

**Temporal connection refused**
Set `USE_TEMPORAL=false` in your `.env` to disable Temporal for local development. The API will run without it.

**`ModuleNotFoundError: No module named 'presidio_analyzer'`**
This is non-fatal. The guardrails middleware will log a warning and pass through without PII scanning. Install with `pip install presidio-analyzer presidio-anonymizer` if you need PII detection.

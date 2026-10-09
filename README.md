# Sentinel — Cyber Threat Dashboard

A SOC-style, full-stack alert triage and threat analytics application built with **React + Vite**, **FastAPI**, **MongoDB**, and **Docker Compose**. It is designed as a portfolio-grade foundation for security operations workflows, with realistic demo telemetry and a documented API.

## Features

- Dark SOC dashboard with summary KPIs, alert trends, and category distribution.
- Live-style alert feed that refreshes every 30 seconds; search and filter by severity/status.
- Alert detail drawer/modal with source, host, detector, description, timestamps, and triage actions.
- Create alerts, assign an analyst, investigate, resolve, or mark false positive.
- CSV export of the currently filtered results.
- FastAPI validation, typed response models, pagination, API docs, health endpoint, analytics endpoints.
- MongoDB persistence, indexed query fields, deterministic demo seed records.
- Docker Compose service health checks, persistent Mongo volume, frontend Nginx reverse proxy, and non-root API process.
- Automated API tests for validation, CRUD/triage, search/filtering, and analytics consistency.

> **Integration note:** This repository includes a generic alert ingestion API and sample events. It does not claim to integrate with analyzers that have not been supplied. Connect your existing analyzers by POSTing normalized events to `POST /api/v1/alerts` or by adding a dedicated adapter.

## Architecture

```text
Browser ── HTTP :8080 ──> Nginx (React static bundle, /api reverse proxy)
                               │
                               └── FastAPI :8000 ──> MongoDB :27017
                                       ├── Alert CRUD and triage
                                       ├── Search/filter
                                       └── Summary, trends, type analytics
```

## Run with Docker Compose

Requirements: Docker Engine/Desktop with the Compose plugin.

```bash
docker compose up --build -d
docker compose ps
```

Open:

- Dashboard: <http://localhost:8080>
- API docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

Stop services while keeping MongoDB data:

```bash
docker compose down
```

Remove services **and** the persisted demo database:

```bash
docker compose down -v
```

The backend seeds six synthetic alerts on first startup when the collection is empty. All IPs/hosts and activity are illustrative; they are not live threat intelligence.

## Run the backend tests

From the repository root:

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

Tests use an in-memory repository and do not require a running MongoDB server. For local backend development without MongoDB, set `STORAGE_MODE=memory` before starting Uvicorn. For the complete UI, use Docker Compose; for Vite dev server, start the API on port 8000 and run `npm install && npm run dev` in `frontend/`.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness and storage mode |
| `GET` | `/api/v1/alerts` | Search/filter/paginate alert feed |
| `GET` | `/api/v1/alerts/{id}` | Fetch alert details |
| `POST` | `/api/v1/alerts` | Ingest a normalized alert |
| `PATCH` | `/api/v1/alerts/{id}` | Update triage status and assignee |
| `GET` | `/api/v1/analytics/summary` | KPI and status/severity counts |
| `GET` | `/api/v1/analytics/trends?days=7` | Daily volume series |
| `GET` | `/api/v1/analytics/types` | Counts grouped by alert category |

Example event:

```json
{
  "title": "Suspicious PowerShell execution",
  "description": "Encoded command launched by an unusual parent process.",
  "severity": "critical",
  "alert_type": "Endpoint Threat",
  "source_ip": "10.14.8.23",
  "host": "ws-fin-044",
  "detector": "edr-behavior"
}
```

Severity values: `critical`, `high`, `medium`, `low`, `info`. Status values: `new`, `investigating`, `resolved`, `false_positive`.

## Configuration

Compose defaults live in `compose.yaml`. Relevant backend environment variables:

- `MONGODB_URI` (default `mongodb://localhost:27017` outside Compose)
- `MONGODB_DATABASE` (default `cyber_soc`)
- `SEED_DEMO_DATA` (`true` by default)
- `STORAGE_MODE=memory` for an in-memory local dev repository
- `ALLOW_MEMORY_FALLBACK=true` only if deliberately allowing fallback when MongoDB is unavailable
- `CORS_ORIGINS` comma-separated list of allowed browser origins

## Security and production-readiness notes

This is a portfolio/demo project, not a production SOC deployment out of the box. Before production use, add authentication and role-based authorization, audit logging, TLS, secrets management, request rate limiting, retention policies, robust ingestion deduplication/idempotency, observability, backups, and schema/index migration practices. Do not expose the unauthenticated write endpoints to the public internet. The current dashboard's 30-second refresh is polling, not a WebSocket/SSE stream. No external threat feed or supplied analyzer is connected by default.

## Project structure

```text
backend/
  app/main.py        FastAPI application, Mongo repository, API, analytics
  tests/test_api.py  API tests using an in-memory repository
  Dockerfile
frontend/
  src/main.jsx       React SOC dashboard and triage interactions
  src/api.js         Typed-ish API access helpers
  src/styles.css     Responsive dashboard UI
  Dockerfile         Vite production build + Nginx
  nginx.conf         SPA fallback and /api reverse proxy
compose.yaml         MongoDB, API, frontend orchestration
```

## License

MIT. See `LICENSE`.

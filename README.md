# Sentinel — Cyber Threat Dashboard

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](backend/)
[![React 18](https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=black)](frontend/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](backend/)
[![MongoDB 7.0](https://img.shields.io/badge/MongoDB-7.0-47A248?logo=mongodb&logoColor=white)](compose.yaml)
[![Docker Compose](https://img.shields.io/badge/docker--compose-2496ED?logo=docker&logoColor=white)](compose.yaml)
[![Tests](https://img.shields.io/badge/tests-20%20passing-brightgreen)](VERIFICATION.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<p align="justify">Sentinel is a full-stack security operations dashboard for alert triage and threat analytics, built with <strong>React + Vite</strong>, <strong>FastAPI</strong>, <strong>MongoDB</strong>, and <strong>Docker Compose</strong>. It models the core workflow of a SOC: detectors emit normalized alerts, analysts triage them through a defined state machine, and the platform surfaces the KPIs and trends a shift lead needs at a glance.</p>

<p align="justify">Three independently deployable services behind one Compose file. The API owns validation, persistence, and analytics; the frontend is a static bundle speaking to the API through a same-origin reverse proxy; MongoDB owns durable state with indexes matched to the query patterns. Every layer is covered by automated tests, and <a href="VERIFICATION.md">VERIFICATION.md</a> documents exactly what has been proven and what has not.</p>

## Contents

- [The 2-minute tour](#the-2-minute-tour)
- [Features](#features)
- [Architecture](#architecture)
- [How a SOC uses this](#how-a-soc-uses-this)
- [Design decisions](#design-decisions)
- [Run with Docker Compose](#run-with-docker-compose)
- [Run the tests](#run-the-tests)
- [API overview](#api-overview)
- [Configuration](#configuration)
- [Verification](#verification)
- [Security and production-readiness notes](#security-and-production-readiness-notes)
- [Roadmap](#roadmap)
- [Project structure](#project-structure)
- [License](#license)

## The 2-minute tour

Start the stack and open the dashboard:

```bash
docker compose up --build -d
# Dashboard: http://localhost:8080
```

Six synthetic alerts are seeded on first launch. Try the analyst loop:

1. **Read the KPIs.** The header shows 6 total alerts, 2 unresolved criticals, 6 open investigations.
2. **Filter to what matters.** Set the severity filter to `critical` — the queue narrows to *Suspicious PowerShell execution* and *Malware hash match*.
3. **Work an alert.** Click *Suspicious PowerShell execution*, review source IP, host, and detector in the detail modal, then hit **Investigate alert**. The toast confirms, the row flips to `investigating`, and the open-investigations KPI moves.
4. **Check the analytics.** The 7-day trend chart and the type-distribution donut reflect the same data the queue shows — one backend, one source of truth.
5. **Export.** Hit **Export report** to download the filtered queue as CSV.

That loop — filter, investigate, verify, export — is the entire Tier-1 analyst workflow, and every step is backed by a tested API call.

## Features

- Dark SOC dashboard with severity KPIs, 7-day alert trends, and category distribution.
- Alert queue with full-text search, severity and status filters, and pagination.
- Alert detail modal with source IP, affected host, detector, timestamps, and triage actions.
- Triage state machine: `new` → `investigating` → `resolved`, plus `false_positive`, with analyst assignment.
- Manual alert ingestion form with server-side validation.
- CSV export of the currently filtered view.
- Analytics endpoints: summary KPIs, daily volume trends, per-category counts.
- MongoDB persistence with indexes on the hot query paths; deterministic demo seed.
- Docker Compose orchestration with healthcheck-gated startup ordering and a persistent data volume.
- Nginx reverse proxy serving the SPA with `/api` routed to the backend (no CORS in production).
- Backend API tests and frontend API-client tests, all passing.

> **Integration note:** This repository ships a generic alert ingestion API and synthetic demo events, plus a working ingestion adapter for [llm-security-log-analyzer](https://github.com/MinuuLakshmi17/llm-security-log-analyzer) in `adapters/`. Point the adapter at a running analyzer and its open findings flow into Sentinel as triageable alerts — see `adapters/README.md`.

## Architecture

```text
Browser ── HTTP :8080 ──> Nginx (React static bundle, /api reverse proxy)
                               │
                               └── FastAPI :8000 ──> MongoDB :27017
                                       ├── Alert CRUD and triage
                                       ├── Search/filter/pagination
                                       └── Summary, trends, type analytics
```

<p align="justify">The frontend never talks to MongoDB and never needs to know the API's host: in production it calls the same origin under <code>/api</code>, which Nginx proxies to the backend service. In development, the Vite dev server provides the identical proxy. One networking model across environments, and an entire class of CORS misconfiguration eliminated.</p>

## How a SOC uses this

<p align="justify">A detection source (EDR rule, network analytic, identity audit) POSTs a normalized alert. It lands in the queue as <code>new</code>. A Tier-1 analyst picks it up, moves it to <code>investigating</code>, and assigns themselves. If it is benign, it becomes <code>false_positive</code> — kept for detector tuning, not deleted, because false-positive rates are how detection quality is measured. If it is real, it is worked to <code>resolved</code>. The dashboard's KPIs (open investigations, unresolved criticals) and the 7-day trend chart are the shift-lead view: they answer "are we keeping up?" at a glance.</p>

## Design decisions

<p align="justify"><strong>MongoDB for alerts, not Postgres.</strong> Alert payloads are semi-structured: different detectors emit different fields, and the schema evolves as new sources are onboarded. A document store absorbs that without migrations, and the query patterns (recency-ordered feeds, severity/status filters, per-day aggregations) map cleanly onto compound indexes. The repository creates indexes on <code>(created_at)</code>, <code>(severity, status)</code>, and <code>(alert_type)</code> at startup — the three shapes the API actually queries.</p>

<p align="justify"><strong>Repository pattern with an in-memory implementation.</strong> The API depends on an <code>AlertRepository</code> interface, not on PyMongo directly. The in-memory implementation lets the full API test suite run in under a second with no database, while production gets the Mongo implementation. The same seam is what a future Postgres or Elasticsearch backend would plug into.</p>

<p align="justify"><strong>Validation at the boundary.</strong> Every ingested alert is validated by Pydantic models before it touches storage: severity and status are closed vocabularies, string lengths are bounded, and triage updates can only move status and assignee — never rewrite history fields. Invalid input gets a 422 with a reason, not a 500.</p>

<p align="justify"><strong>Polling, honestly labeled.</strong> The dashboard refreshes every 30 seconds via polling. For a triage queue this is a defensible tradeoff (alerts are human-timescale events), and the roadmap names the real upgrade: Server-Sent Events or WebSockets for push delivery. The code does not pretend to be realtime.</p>

<p align="justify"><strong>Non-root containers and health-gated startup.</strong> The API image runs as an unprivileged user, and Compose waits for MongoDB's healthcheck before starting the API, and the API's before the frontend — so the first request never races a cold database.</p>

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

## Run the tests

Backend (in-memory repository, no MongoDB needed):

```bash
cd backend
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

Frontend (Vitest, mocked fetch — no browser or backend needed):

```bash
cd frontend
npm install
npm test
npm run build
```

Adapter mapping tests (stdlib only — any Python 3.10+ works):

```bash
python -m pytest adapters/tests/ -q
```

For local backend development without MongoDB, set `STORAGE_MODE=memory` before starting Uvicorn. For the complete UI, use Docker Compose; for the Vite dev server, start the API on port 8000 and run `npm run dev` in `frontend/`.

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

## Verification

See [VERIFICATION.md](VERIFICATION.md) for the full report: what was tested (backend and frontend suites, production bundle, live API end-to-end), what was fixed along the way, and what remains unverified (containerized run, in-browser pass, public deployment).

## Security and production-readiness notes

This is a portfolio/demo project, not a production SOC deployment out of the box. Before production use, add authentication and role-based authorization, audit logging, TLS, secrets management, request rate limiting, retention policies, robust ingestion deduplication/idempotency, observability, backups, and schema/index migration practices. Do not expose the unauthenticated write endpoints to the public internet. No external threat feed or supplied analyzer is connected by default.

## Roadmap

- [x] Ingestion adapter for llm-security-log-analyzer (normalized event mapping, idempotent forwarding).
- [ ] Ingestion adapters for additional detectors (intelligent-network-threat-detection).
- [ ] Authentication with analyst/admin roles and an audit trail for triage actions.
- [ ] Push delivery via Server-Sent Events or WebSockets instead of polling.
- [ ] Browser end-to-end tests and a validated `docker compose` run.
- [ ] Public deployment with managed database, secrets, TLS, and health monitoring.

## Project structure

```text
backend/
  app/main.py        FastAPI application, Mongo repository, API, analytics
  tests/test_api.py  API tests using an in-memory repository
  Dockerfile         Non-root Python image with healthcheck
frontend/
  src/main.jsx       React SOC dashboard and triage interactions
  src/api.js         API access helpers
  src/api.test.js    API client contract tests (Vitest)
  src/styles.css     Responsive dashboard UI
  Dockerfile         Multi-stage Vite build + Nginx
  nginx.conf         SPA fallback and /api reverse proxy
adapters/
  forward_analyzer_alerts.py  Analyzer -> Sentinel forwarder (stdlib only)
  tests/test_forward.py       Mapping unit tests
  README.md                   Field mapping and usage
compose.yaml         MongoDB, API, frontend orchestration
VERIFICATION.md      Honest verification report
```

## License

MIT. See `LICENSE`.

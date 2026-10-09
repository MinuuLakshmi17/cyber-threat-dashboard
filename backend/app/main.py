from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

SEVERITIES = ("critical", "high", "medium", "low", "info")
STATUSES = ("new", "investigating", "resolved", "false_positive")

class AlertCreate(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    description: str = Field(min_length=5, max_length=4000)
    severity: Literal["critical", "high", "medium", "low", "info"]
    alert_type: str = Field(min_length=2, max_length=80)
    source_ip: str = Field(min_length=3, max_length=64)
    host: str = Field(min_length=1, max_length=160)
    detector: str = Field(default="manual", max_length=100)

class AlertStatusUpdate(BaseModel):
    status: Literal["new", "investigating", "resolved", "false_positive"]
    assignee: Optional[str] = Field(default=None, max_length=120)

class Alert(AlertCreate):
    id: str
    status: str = "new"
    assignee: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AlertRepository:
    """Mongo-backed repository with an in-memory mode for tests/local development."""
    def __init__(self, uri: str | None = None, database: str = "cyber_soc", use_memory: bool = False):
        self._memory = use_memory
        self._items: dict[str, dict] = {}
        self._collection = None
        if not use_memory and uri:
            from pymongo import MongoClient
            self._client = MongoClient(uri, serverSelectionTimeoutMS=2500, tz_aware=True)
            self._client.admin.command("ping")
            self._collection = self._client[database]["alerts"]
            self._collection.create_index([("created_at", -1)])
            self._collection.create_index([("severity", 1), ("status", 1)])
            self._collection.create_index([("alert_type", 1)])

    def insert(self, doc: dict) -> dict:
        if self._collection is not None:
            self._collection.insert_one(doc.copy())
        else:
            self._items[doc["id"]] = doc.copy()
        return doc

    def all(self) -> list[dict]:
        if self._collection is not None:
            return list(self._collection.find({}, {"_id": 0}).sort("created_at", -1))
        return sorted(self._items.values(), key=lambda x: x["created_at"], reverse=True)

    def get(self, alert_id: str) -> dict | None:
        if self._collection is not None:
            return self._collection.find_one({"id": alert_id}, {"_id": 0})
        return self._items.get(alert_id)

    def update(self, alert_id: str, changes: dict) -> dict | None:
        if self._collection is not None:
            result = self._collection.find_one_and_update({"id": alert_id}, {"$set": changes}, return_document=True, projection={"_id": 0})
            return result
        if alert_id not in self._items:
            return None
        self._items[alert_id].update(changes)
        return self._items[alert_id].copy()

    def count(self) -> int:
        return self._collection.count_documents({}) if self._collection is not None else len(self._items)


def make_alert(data: AlertCreate, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    return {"id": str(uuid4()), **data.model_dump(), "status": "new", "assignee": None, "created_at": now, "updated_at": now}


def create_app(repository: AlertRepository | None = None, seed: bool = False) -> FastAPI:
    app = FastAPI(title="Sentinel SOC API", version="1.0.0", description="Alert triage and analytics API for a security operations dashboard.")
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins], allow_credentials=False, allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["*"])
    if repository is None:
        uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        if os.getenv("STORAGE_MODE", "mongo") == "memory":
            repository = AlertRepository(use_memory=True)
        else:
            try:
                repository = AlertRepository(uri, os.getenv("MONGODB_DATABASE", "cyber_soc"))
            except ModuleNotFoundError:
                # Keeps the API importable for unit tests and minimal local development.
                # Container images install pymongo; connection failures still fail loudly by default.
                repository = AlertRepository(use_memory=True)
            except Exception:
                if os.getenv("ALLOW_MEMORY_FALLBACK", "false").lower() == "true":
                    repository = AlertRepository(use_memory=True)
                else:
                    raise
    app.state.repository = repository
    if seed and repository.count() == 0:
        now = datetime.now(timezone.utc)
        examples = [
            ("Credential stuffing detected", "Repeated authentication failures against multiple accounts.", "high", "Identity Attack", "185.199.110.42", "idp-prod-01", "auth-anomaly"),
            ("Suspicious PowerShell execution", "Encoded command launched by an unusual parent process.", "critical", "Endpoint Threat", "10.14.8.23", "ws-fin-044", "edr-behavior"),
            ("Possible DNS tunneling", "High-entropy DNS queries to a newly observed domain.", "medium", "Network Anomaly", "10.14.3.18", "dns-resolver-02", "dns-analytics"),
            ("Unexpected privilege escalation", "A service account was added to a privileged group.", "high", "Privilege Escalation", "10.14.9.71", "ad-controller-01", "identity-audit"),
            ("Known scanner activity", "Port scan pattern matched internal reconnaissance rule.", "low", "Reconnaissance", "203.0.113.88", "vpn-gateway-01", "netflow-rule"),
            ("Malware hash match", "File hash matched a locally maintained threat-intelligence indicator.", "critical", "Malware", "10.14.4.52", "eng-laptop-017", "ioc-match"),
        ]
        for i, row in enumerate(examples):
            title, desc, sev, typ, ip, host, detector = row
            item = make_alert(AlertCreate(title=title, description=desc, severity=sev, alert_type=typ, source_ip=ip, host=host, detector=detector), now - timedelta(minutes=i * 17))
            repository.insert(item)
    @app.get("/health")
    def health():
        return {"status": "ok", "service": "sentinel-soc-api", "storage": "mongo" if repository._collection is not None else "memory"}

    @app.get("/api/v1/alerts", response_model=list[Alert])
    def list_alerts(q: str | None = Query(default=None, max_length=200), severity: str | None = None, alert_type: str | None = None, status_filter: str | None = Query(default=None, alias="status"), since_hours: int | None = Query(default=None, ge=1, le=8760), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
        if severity and severity not in SEVERITIES: raise HTTPException(422, "Invalid severity")
        if status_filter and status_filter not in STATUSES: raise HTTPException(422, "Invalid status")
        items = repository.all()
        if q:
            needle = q.casefold()
            items = [a for a in items if any(needle in str(a.get(k, "")).casefold() for k in ("title", "description", "source_ip", "host", "alert_type", "detector"))]
        if severity: items = [a for a in items if a["severity"] == severity]
        if alert_type: items = [a for a in items if a["alert_type"].casefold() == alert_type.casefold()]
        if status_filter: items = [a for a in items if a["status"] == status_filter]
        if since_hours:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
            items = [a for a in items if a["created_at"] >= cutoff]
        return items[offset:offset + limit]

    @app.get("/api/v1/alerts/{alert_id}", response_model=Alert)
    def get_alert(alert_id: str):
        item = repository.get(alert_id)
        if not item: raise HTTPException(404, "Alert not found")
        return item

    @app.post("/api/v1/alerts", response_model=Alert, status_code=status.HTTP_201_CREATED)
    def create_alert(payload: AlertCreate):
        item = repository.insert(make_alert(payload))
        return item

    @app.patch("/api/v1/alerts/{alert_id}", response_model=Alert)
    def update_alert(alert_id: str, payload: AlertStatusUpdate):
        changes = {"status": payload.status, "assignee": payload.assignee, "updated_at": datetime.now(timezone.utc)}
        item = repository.update(alert_id, changes)
        if not item: raise HTTPException(404, "Alert not found")
        return item

    @app.get("/api/v1/analytics/summary")
    def analytics_summary():
        items = repository.all()
        return {"total": len(items), "open": sum(a["status"] in ("new", "investigating") for a in items), "critical": sum(a["severity"] == "critical" and a["status"] != "resolved" for a in items), "resolved": sum(a["status"] == "resolved" for a in items), "by_severity": {s: sum(a["severity"] == s for a in items) for s in SEVERITIES}, "by_status": {s: sum(a["status"] == s for a in items) for s in STATUSES}}

    @app.get("/api/v1/analytics/trends")
    def analytics_trends(days: int = Query(default=7, ge=1, le=90)):
        now = datetime.now(timezone.utc)
        items = repository.all()
        result = []
        for back in range(days - 1, -1, -1):
            day = (now - timedelta(days=back)).date()
            bucket = [a for a in items if a["created_at"].date() == day]
            result.append({"date": day.isoformat(), "total": len(bucket), **{s: sum(a["severity"] == s for a in bucket) for s in SEVERITIES}})
        return result

    @app.get("/api/v1/analytics/types")
    def analytics_types():
        counts: dict[str, int] = {}
        for item in repository.all(): counts[item["alert_type"]] = counts.get(item["alert_type"], 0) + 1
        return sorted([{"type": key, "count": value} for key, value in counts.items()], key=lambda x: (-x["count"], x["type"]))
    return app

app = create_app(seed=os.getenv("SEED_DEMO_DATA", "true").lower() == "true")

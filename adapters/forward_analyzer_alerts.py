#!/usr/bin/env python3
"""Forward open findings from llm-security-log-analyzer into Sentinel.

The analyzer (detection engine over security logs) exposes its findings at
``GET /alerts?status=open``. This script polls that endpoint, maps each
finding onto Sentinel's normalized alert schema, and ingests it via
``POST /api/v1/alerts``. Forwarded analyzer alert IDs are recorded in a
state file, so reruns are idempotent: each finding is forwarded exactly once.

Severity vocabularies align 1:1 (critical/high/medium/low), so no remapping
is needed. Only ``open`` findings are forwarded; acknowledged or resolved
ones stay in the analyzer.

Usage:
    python adapters/forward_analyzer_alerts.py \
        --analyzer http://localhost:8001 \
        --sentinel http://localhost:8000

    # preview without posting anything
    python adapters/forward_analyzer_alerts.py --dry-run

Stdlib only: no third-party dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_STATE = Path(__file__).with_name("forwarded.json")


def _get(base: str, path: str, params: dict | None = None) -> object:
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"GET {url} failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"GET {url} failed: {exc.reason}") from exc


def _post(base: str, path: str, payload: dict) -> dict:
    url = base.rstrip("/") + path
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise SystemExit(f"POST {url} failed: HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"POST {url} failed: {exc.reason}") from exc


def to_sentinel(finding: dict) -> dict:
    """Map one analyzer AlertOut onto Sentinel's AlertCreate schema."""
    rule_id = str(finding.get("rule_id") or "unknown")
    alert_type = rule_id.replace("_", " ").replace("-", " ").title().strip()[:80] or "Detection"
    evidence = finding.get("evidence") or []
    first = evidence[0] if isinstance(evidence, list) and evidence and isinstance(evidence[0], dict) else {}
    source_ip = str(first.get("source_ip") or "unknown")[:64]
    host = str(first.get("host") or first.get("hostname") or "unknown")[:160]

    lines = [
        f"Rule {rule_id} · risk score {finding.get('risk_score', '?')}/100",
        f"{len(evidence)} evidence event(s) attached in the analyzer.",
    ]
    if finding.get("llm_summary"):
        lines += ["", "LLM assessment:", str(finding["llm_summary"])]
    recommendations = finding.get("llm_recommendations") or []
    if recommendations:
        lines += ["", "Recommended actions:"]
        lines += [f"- {r}" for r in recommendations[:5]]

    title = str(finding.get("title") or "Security finding").strip()[:180]
    if len(title) < 4:
        title = "Security finding"
    description = "\n".join(lines)[:4000]
    if len(description) < 5:
        description = "Forwarded from llm-security-log-analyzer."

    return {
        "title": title,
        "description": description,
        "severity": finding.get("severity") or "low",
        "alert_type": alert_type,
        "source_ip": source_ip,
        "host": host,
        "detector": f"log-analyzer:{rule_id}"[:100],
    }


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
    return {}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Forward analyzer findings into Sentinel.")
    parser.add_argument("--analyzer", default="http://localhost:8001",
                        help="base URL of llm-security-log-analyzer (default: http://localhost:8001)")
    parser.add_argument("--sentinel", default="http://localhost:8000",
                        help="base URL of the Sentinel API (default: http://localhost:8000)")
    parser.add_argument("--state", default=str(DEFAULT_STATE),
                        help="JSON file recording forwarded alert IDs (default: adapters/forwarded.json)")
    parser.add_argument("--limit", type=int, default=100, help="max findings to pull per run")
    parser.add_argument("--dry-run", action="store_true", help="print the mapped alerts without posting")
    args = parser.parse_args(argv)

    state_path = Path(args.state)
    forwarded: dict = load_state(state_path)

    findings = _get(args.analyzer, "/alerts", {"status": "open", "limit": args.limit})
    if not isinstance(findings, list):
        raise SystemExit(f"unexpected /alerts response: {findings!r:.200}")

    new, skipped = 0, 0
    for finding in findings:
        aid = str(finding.get("id"))
        if aid in forwarded:
            skipped += 1
            continue
        payload = to_sentinel(finding)
        if args.dry_run:
            print(json.dumps(payload, indent=2))
        else:
            created = _post(args.sentinel, "/api/v1/alerts", payload)
            forwarded[aid] = created["id"]
            print(f"forwarded analyzer alert {aid} -> sentinel {created['id']}: {payload['title']}")
        new += 1

    if not args.dry_run:
        save_state(state_path, forwarded)
    print(f"done: {new} forwarded, {skipped} already forwarded, {len(findings)} open findings total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

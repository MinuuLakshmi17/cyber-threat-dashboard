# Ingestion adapters

Bridges that forward findings from external detectors into Sentinel's
normalized alert API. Each adapter is a small stdlib-only script: poll the
source, map its schema onto `POST /api/v1/alerts`, and record forwarded IDs
so reruns are idempotent.

## `forward_analyzer_alerts.py`

Forwards open findings from
[llm-security-log-analyzer](https://github.com/MinuuLakshmi17/llm-security-log-analyzer)
— the detection engine over security logs — into Sentinel.

```bash
# the analyzer on :8001, Sentinel on :8000
python adapters/forward_analyzer_alerts.py \
    --analyzer http://localhost:8001 \
    --sentinel http://localhost:8000

# preview the mapped alerts without posting anything
python adapters/forward_analyzer_alerts.py --dry-run
```

**Field mapping:**

| Analyzer (`AlertOut`) | Sentinel (`AlertCreate`) | Notes |
|---|---|---|
| `title` | `title` | truncated to 180 chars |
| `rule_id` + `risk_score` + `llm_summary` + `llm_recommendations` | `description` | risk score, evidence count, LLM assessment and recommended actions |
| `severity` | `severity` | 1:1 — both use critical/high/medium/low |
| `rule_id` | `alert_type` | `brute_force` → `Brute Force` |
| `evidence[0].source_ip` | `source_ip` | `unknown` when evidence is empty |
| `evidence[0].host` | `host` | `unknown` when evidence is empty |
| `rule_id` | `detector` | prefixed: `log-analyzer:brute_force` |

Only findings with status `open` are forwarded; acknowledged and resolved
ones stay in the analyzer. Forwarded analyzer alert IDs are stored in
`adapters/forwarded.json` (override with `--state`), so each finding is
forwarded exactly once.

**Tests:** `python -m pytest adapters/tests/ -q` — 10 mapping unit tests
(field mapping, fallbacks, constraint satisfaction, corrupt state handling).
The full forward → dedup cycle was additionally verified live against a
running Sentinel backend.

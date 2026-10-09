"""Mapping unit tests for the analyzer -> Sentinel forwarder."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from forward_analyzer_alerts import to_sentinel, load_state  # noqa: E402


def finding(**overrides):
    base = {
        "id": 7, "rule_id": "brute_force", "title": "Brute-force campaign",
        "severity": "high", "risk_score": 72, "status": "open",
        "evidence": [{"source_ip": "203.0.113.88", "host": "vpn-gateway-01"}],
        "llm_summary": None, "llm_recommendations": None,
    }
    base.update(overrides)
    return base


def test_rule_id_becomes_title_case_alert_type():
    assert to_sentinel(finding(rule_id="concurrent_access"))["alert_type"] == "Concurrent Access"


def test_severity_passes_through_unchanged():
    for sev in ("critical", "high", "medium", "low"):
        assert to_sentinel(finding(severity=sev))["severity"] == sev


def test_evidence_supplies_source_ip_and_host():
    out = to_sentinel(finding())
    assert out["source_ip"] == "203.0.113.88"
    assert out["host"] == "vpn-gateway-01"


def test_missing_evidence_falls_back_to_unknown():
    out = to_sentinel(finding(evidence=[]))
    assert out["source_ip"] == "unknown"
    assert out["host"] == "unknown"


def test_llm_enrichment_lands_in_description():
    out = to_sentinel(finding(llm_summary="Two-country login in 12 minutes.",
                             llm_recommendations=["Rotate the password"]))
    assert "Two-country login" in out["description"]
    assert "Rotate the password" in out["description"]
    assert "72/100" in out["description"]


def test_detector_names_the_source_rule():
    assert to_sentinel(finding())["detector"] == "log-analyzer:brute_force"


def test_output_satisfies_sentinel_field_constraints():
    out = to_sentinel(finding())
    assert 4 <= len(out["title"]) <= 180
    assert 5 <= len(out["description"]) <= 4000
    assert 2 <= len(out["alert_type"]) <= 80
    assert 3 <= len(out["source_ip"]) <= 64
    assert 1 <= len(out["host"]) <= 160


def test_short_title_gets_safe_fallback():
    out = to_sentinel(finding(title="x"))
    assert len(out["title"]) >= 4


def test_load_state_missing_file_returns_empty(tmp_path):
    assert load_state(tmp_path / "nope.json") == {}


def test_load_state_corrupt_file_returns_empty(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json")
    assert load_state(p) == {}

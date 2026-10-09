from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import AlertCreate, AlertRepository, create_app


def client_with_seed():
    repo = AlertRepository(use_memory=True)
    app = create_app(repo, seed=True)
    return TestClient(app), repo


def test_health_and_seed_data():
    client, _ = client_with_seed()
    r = client.get('/health')
    assert r.status_code == 200 and r.json()['status'] == 'ok'
    alerts = client.get('/api/v1/alerts').json()
    assert len(alerts) == 6
    assert alerts[0]['created_at'] >= alerts[-1]['created_at']


def test_search_and_filters():
    client, _ = client_with_seed()
    assert len(client.get('/api/v1/alerts', params={'severity': 'critical'}).json()) == 2
    assert len(client.get('/api/v1/alerts', params={'q': 'powershell'}).json()) == 1
    assert len(client.get('/api/v1/alerts', params={'status': 'resolved'}).json()) == 0
    assert client.get('/api/v1/alerts', params={'severity': 'impossible'}).status_code == 422


def test_create_update_and_not_found():
    client, _ = client_with_seed()
    payload = {'title':'Test suspicious login', 'description':'Multiple failures in a short window', 'severity':'medium', 'alert_type':'Identity Attack', 'source_ip':'192.0.2.7', 'host':'test-host'}
    created = client.post('/api/v1/alerts', json=payload)
    assert created.status_code == 201
    aid = created.json()['id']
    updated = client.patch(f'/api/v1/alerts/{aid}', json={'status':'investigating','assignee':'analyst@example.test'})
    assert updated.status_code == 200
    assert updated.json()['status'] == 'investigating'
    assert updated.json()['assignee'] == 'analyst@example.test'
    assert client.patch('/api/v1/alerts/nope', json={'status':'resolved'}).status_code == 404


def test_validation_rejects_bad_payload():
    client, _ = client_with_seed()
    assert client.post('/api/v1/alerts', json={'title':'x'}).status_code == 422


def test_analytics_are_consistent():
    client, _ = client_with_seed()
    summary = client.get('/api/v1/analytics/summary').json()
    assert summary['total'] == 6
    assert sum(summary['by_severity'].values()) == 6
    assert sum(summary['by_status'].values()) == 6
    assert len(client.get('/api/v1/analytics/trends', params={'days':7}).json()) == 7
    assert sum(x['count'] for x in client.get('/api/v1/analytics/types').json()) == 6

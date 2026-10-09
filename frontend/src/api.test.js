import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from './api';

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  it('builds the alerts query string and omits empty filters', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => [] });
    await api.alerts({ q: 'powershell', severity: 'critical', status: '', limit: 200 });
    const url = fetch.mock.calls[0][0];
    expect(url).toContain('/v1/alerts?');
    expect(url).toContain('q=powershell');
    expect(url).toContain('severity=critical');
    expect(url).toContain('limit=200');
    expect(url).not.toContain('status=');
  });

  it('throws the backend detail message on error responses', async () => {
    fetch.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'Invalid severity' }) });
    await expect(api.summary()).rejects.toThrow('Invalid severity');
  });

  it('falls back to a generic message when the error body is not JSON', async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: async () => { throw new Error('no json'); } });
    await expect(api.types()).rejects.toThrow('Request failed (500)');
  });

  it('sends PATCH with a JSON body for status updates', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    await api.updateAlert('abc-123', { status: 'investigating', assignee: null });
    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain('/v1/alerts/abc-123');
    expect(options.method).toBe('PATCH');
    expect(JSON.parse(options.body)).toEqual({ status: 'investigating', assignee: null });
  });

  it('sends POST with a JSON body for alert creation', async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const payload = { title: 'Test alert', severity: 'high' };
    await api.createAlert(payload);
    const [url, options] = fetch.mock.calls[0];
    expect(url).toContain('/v1/alerts');
    expect(options.method).toBe('POST');
    expect(JSON.parse(options.body)).toEqual(payload);
  });
});

"""Exercise the worker's own SDK client without running imports or sending emails."""
import asyncio
import json
from pathlib import Path
import runpy

import httpx

from services import supabase_http


def test_worker_recovers_read_and_publishes_heartbeat(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.RemoteProtocolError('ConnectionTerminated')
        if request.method == 'POST':
            return httpx.Response(201, json=[json.loads(request.content)])
        return httpx.Response(200, json=[{'id': 'local-1'}])

    with supabase_http.SupabaseReadRetryClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setenv('SUPABASE_URL', 'https://worker-test.supabase.co')
        monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'test-only-key')
        monkeypatch.setattr(supabase_http, 'SupabaseReadRetryClient', lambda: http)
        worker = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'worker_importacion.py'))
        client = worker['supabase']
        assert client is not None
        assert client.table('locales').select('id').execute().data == [{'id': 'local-1'}]
        asyncio.run(worker['update_heartbeat']())

    assert [request.method for request in requests] == ['GET', 'GET', 'POST']
    assert requests[-1].url.path == '/rest/v1/system_health'
    assert json.loads(requests[-1].content)['key'] == 'CRON_LAST_RUN'

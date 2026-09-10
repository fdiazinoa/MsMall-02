import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import main
from services.supabase_http import SupabaseReadRetryClient


def test_read_recovers_after_connection_termination():
    calls = []

    def handler(request):
        calls.append(request.method)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError('ConnectionTerminated')
        return httpx.Response(200, json=[{'id': 'mall-1'}])

    with SupabaseReadRetryClient(transport=httpx.MockTransport(handler)) as client:
        assert client.get('https://example.test/malls').json() == [{'id': 'mall-1'}]
    assert calls == ['GET', 'GET']


@pytest.mark.parametrize('method,expected', [('GET', 2), ('POST', 1), ('PATCH', 1), ('DELETE', 1)])
def test_retry_is_bounded_and_never_replays_mutations(method, expected):
    calls = []

    def handler(request):
        calls.append(request.method)
        raise httpx.ReadError('connection lost')

    with SupabaseReadRetryClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadError):
            client.request(method, 'https://example.test/data')
    assert len(calls) == expected


def test_invalid_credentials_are_not_retried():
    calls = []

    def handler(request):
        calls.append(request.method)
        return httpx.Response(401)

    with SupabaseReadRetryClient(transport=httpx.MockTransport(handler)) as client:
        assert client.get('https://example.test/auth').status_code == 401
    assert calls == ['GET']


@pytest.mark.parametrize('error,status', [(httpx.ConnectError('offline'), 503), (RuntimeError('invalid token'), 401)])
def test_auth_distinguishes_connection_failure_from_invalid_session(monkeypatch, error, status):
    def get_user(token):
        raise error

    monkeypatch.setattr(main, 'supabase', SimpleNamespace(auth=SimpleNamespace(get_user=get_user)))
    with pytest.raises(HTTPException) as result:
        main.get_current_user_id(HTTPAuthorizationCredentials(scheme='Bearer', credentials='test'))
    assert result.value.status_code == status
    if status == 503:
        assert result.value.headers == {'Retry-After': '2'}

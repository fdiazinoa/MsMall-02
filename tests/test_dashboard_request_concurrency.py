"""Exercise the real endpoint definitions without starting production services."""
import ast
import asyncio
import logging
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


@pytest.mark.parametrize('target', ['get_sales_gaps', 'get_my_malls', 'get_current_user_id', '_get_access_context'])
def test_slow_database_request_does_not_block_other_requests(target):
    entered, release = threading.Event(), threading.Event()

    def slow_result(*_args):
        entered.set()
        release.wait(2)
        return SimpleNamespace(data=[], user=SimpleNamespace(id='user-1'))

    class Query:
        def __getattr__(self, name):
            return slow_result if name == 'execute' else lambda *_a, **_k: self

    async def scenario():
        app = FastAPI()
        namespace = dict(
            app=app, Depends=Depends, HTTPException=HTTPException,
            HTTPAuthorizationCredentials=HTTPAuthorizationCredentials,
            security=HTTPBearer(), Optional=Optional, Dict=Dict, Any=Any,
            datetime=datetime, logger=logging.getLogger(__name__), asyncio=asyncio,
            get_current_mall=lambda: 'mall-1', get_current_user_id=lambda: 'user-1',
            expected_sales_dates=lambda *_a: set(), _is_store_active=lambda _s: True,
            load_actual_sales_dates_by_local=lambda *_a, **_k: {},
            supabase=SimpleNamespace(table=lambda *_a: Query(), auth=SimpleNamespace(get_user=slow_result)),
            _get_access_context_sync=slow_result,
        )
        tree = ast.parse((Path(__file__).parents[1] / 'main.py').read_text())
        node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == target)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'main.py', 'exec'), namespace)
        if target == 'get_current_user_id':
            @app.get('/subject')
            async def subject(user_id=Depends(namespace[target])):
                return {'user_id': user_id}
            url = '/subject'
        elif target == '_get_access_context':
            @app.get('/subject')
            async def subject():
                await namespace[target]('user-1')
                return {'ok': True}
            url = '/subject'
        elif target == 'get_my_malls':
            url = '/api/v1/users/me/malls'
        else:
            url = '/api/v1/auditoria/brechas-ventas?local_id=ALL&fecha_inicio=2026-04-01&fecha_fin=2026-09-07'

        @app.get('/probe')
        async def probe():
            return {'ok': True}

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            pending = asyncio.create_task(client.get(url, headers={'Authorization': 'Bearer test'}))
            try:
                for _ in range(200):
                    if entered.is_set():
                        break
                    await asyncio.sleep(.005)
                assert entered.is_set(), 'Database operation was not reached'
                response = await asyncio.wait_for(client.get('/probe'), timeout=.5)
                assert response.status_code == 200
                assert not pending.done(), 'The probe only ran after the slow operation completed'
            finally:
                release.set()
                result = await pending
            assert result.status_code == 200

    asyncio.run(scenario())

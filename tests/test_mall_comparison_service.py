import ast
import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
from fastapi import HTTPException

from services.mall_comparison_service import MallComparisonService


class Query:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.mall_ids = None
        self.mall_id = None

    def select(self, *_args):
        return self

    def in_(self, _field, values):
        self.mall_ids = values
        return self

    def eq(self, _field, value):
        self.mall_id = value
        return self

    def execute(self):
        if self.table == 'malls':
            return SimpleNamespace(data=[row for row in self.database.malls if row['id'] in self.mall_ids])
        return SimpleNamespace(data=self.database.locales.get(self.mall_id, []))


class RpcQuery:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return SimpleNamespace(data=self.data)


class Database:
    malls = [
        {'id': 'mall-a', 'nombre': 'Ágora', 'conf_locale': 'es-DO', 'conf_moneda': 'DOP'},
        {'id': 'mall-b', 'nombre': 'Central', 'conf_locale': 'es-DO', 'conf_moneda': 'DOP'},
    ]
    locales = {
        'mall-a': [
            {'id': 'a-1', 'nombre': 'Uno', 'rubro': 'Moda', 'tipo_negocio': 'Tienda'},
            {'id': 'a-2', 'nombre': 'Dos', 'rubro': None, 'tipo_negocio': None},
        ],
        'mall-b': [{'id': 'b-1', 'nombre': 'Tres', 'rubro': 'Comida', 'tipo_negocio': 'Restaurante'}],
    }
    metrics = {
        'mall-a': [
            {'local_id': 'a-1', 'total_bruto': 120, 'total_neto': 100, 'transacciones': 3},
            {'out_local_id': 'a-2', 'out_total_bruto': 30, 'out_total_neto': 25, 'out_transacciones': 1},
        ],
        'mall-b': [{'local_id': 'b-1', 'total_bruto': 90, 'total_neto': 75, 'transacciones': 2}],
    }

    def table(self, name):
        return Query(self, name)

    def rpc(self, name, params):
        assert name == 'get_metricas_periodo'
        assert params['fecha_inicio_param'] == '2026-09-01'
        assert params['fecha_fin_param'] == '2026-09-08'
        return RpcQuery(self.metrics[params['mall_id_param']])


def test_comparison_aggregates_malls_stores_rubros_and_categories():
    result = MallComparisonService(Database()).load(['mall-a', 'mall-b'], '2026-09-01', '2026-09-08')

    assert [mall['nombre'] for mall in result['malls']] == ['Ágora', 'Central']
    agora = result['malls'][0]
    assert agora['total_bruto'] == 150
    assert agora['total_neto'] == 125
    assert agora['transacciones'] == 4
    assert agora['ticket_promedio'] == 37.5
    assert agora['locales'][0]['id'] == 'a-1'
    assert {row['nombre'] for row in agora['rubros']} == {'Moda', 'Sin rubro'}
    assert {row['nombre'] for row in agora['categorias']} == {'Tienda', 'Sin categoría'}
    assert sum(row['cantidad_locales'] for row in agora['rubros']) == 2


def test_comparison_rejects_unknown_mall():
    with pytest.raises(ValueError, match='no existen'):
        MallComparisonService(Database()).load(['mall-a', 'missing'], '2026-09-01', '2026-09-08')


def endpoint_namespace(allowed_malls):
    source = (Path(__file__).parents[1] / 'main.py').read_text()
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.AsyncFunctionDef) and item.name == 'get_mall_comparison')

    class App:
        def get(self, _path):
            return lambda function: function

    class Comparison:
        def __init__(self, _database):
            pass

        def load(self, mall_ids, start_date, end_date):
            return {'start_date': start_date, 'end_date': end_date, 'malls': mall_ids}

    namespace = {
        'app': App(), 'Query': lambda *_args, **_kwargs: None, 'Depends': lambda dependency: dependency,
        'require_module_permission': lambda *_args: None, 'List': List, 'Dict': Dict, 'Any': Any,
        'date': date, 'HTTPException': HTTPException, 'asyncio': asyncio,
        '_get_user_mall_ids': lambda _user_id: allowed_malls, 'supabase': object(),
        'MallComparisonService': Comparison, 'logger': SimpleNamespace(error=lambda *_args: None),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'main.py', 'exec'), namespace)
    return namespace['get_mall_comparison']


def test_endpoint_rejects_a_mall_outside_user_assignments():
    endpoint = endpoint_namespace(['mall-a'])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(endpoint('2026-09-01', '2026-09-08', ['mall-a', 'mall-b'], {'user_id': 'user-1', 'legacy_role': 'auditor'}))
    assert exc.value.status_code == 403


def test_endpoint_allows_authorized_malls_and_admins():
    endpoint = endpoint_namespace(['mall-a', 'mall-b'])
    response = asyncio.run(endpoint('2026-09-01', '2026-09-08', ['mall-a', 'mall-b'], {'user_id': 'user-1', 'legacy_role': 'auditor'}))
    assert response['malls'] == ['mall-a', 'mall-b']

    admin_endpoint = endpoint_namespace([])
    response = asyncio.run(admin_endpoint('2026-09-01', '2026-09-08', ['mall-a', 'mall-b'], {'user_id': 'admin', 'legacy_role': 'admin'}))
    assert response['malls'] == ['mall-a', 'mall-b']

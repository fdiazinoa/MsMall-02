import asyncio
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from fastapi import HTTPException

from services.local_custom_fields_service import EMPTY_GROUP_LABEL, LocalCustomFieldsService


class _FakeResponse:
    def __init__(self, data=None):
        self.data = data


class _TableQuery:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self._filters = []
        self._order = None
        self._mode = "select"
        self._payload = None
        self._single = False
        self._maybe_single = False

    def select(self, *_args, **_kwargs):
        self._mode = "select"
        return self

    def eq(self, key, value):
        self._filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self._filters.append(("in", key, list(values)))
        return self

    def order(self, column, desc=False):
        self._order = (column, bool(desc))
        return self

    def maybe_single(self):
        self._maybe_single = True
        return self

    def single(self):
        self._single = True
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def _apply_filters(self, rows):
        result = list(rows)
        for op, key, value in self._filters:
            if op == "eq":
                result = [row for row in result if row.get(key) == value]
            elif op == "in":
                result = [row for row in result if row.get(key) in value]
        return result

    def execute(self):
        rows = self.supabase.tables.setdefault(self.table_name, [])
        filtered = self._apply_filters(rows)

        if self._mode == "select":
            data = list(filtered)
            if self._order:
                col, desc = self._order
                data = sorted(data, key=lambda row: (row.get(col) is None, row.get(col)), reverse=desc)
            if self._single:
                return _FakeResponse(dict(data[0]) if data else None)
            if self._maybe_single:
                # supabase-py can return None (not a response with data=None)
                # when maybe_single finds no matching record.
                return _FakeResponse(dict(data[0])) if data else None
            return _FakeResponse([dict(row) for row in data])

        if self._mode == "insert":
            payload = dict(self._payload or {})
            rows.append(payload)
            return _FakeResponse(dict(payload))

        if self._mode == "update":
            updated = []
            for row in rows:
                if row in filtered:
                    row.update(dict(self._payload or {}))
                    updated.append(dict(row))
            return _FakeResponse(updated)

        if self._mode == "delete":
            self.supabase.tables[self.table_name] = [row for row in rows if row not in filtered]
            return _FakeResponse([])

        return _FakeResponse([])


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables

    def table(self, table_name):
        return _TableQuery(self, table_name)


def _guard(operator_ctx, mall_id):
    allowed = set(operator_ctx.get("allowed_malls") or [])
    if operator_ctx.get("role") != "admin" and mall_id not in allowed:
        raise HTTPException(status_code=403, detail="forbidden")


def _service():
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-a", "mall_id": "mall-1", "nombre": "Zara"},
            {"id": "local-b", "mall_id": "mall-1", "nombre": "Mango"},
            {"id": "local-c", "mall_id": "mall-1", "nombre": "Pull&Bear"},
        ],
        "local_custom_field_definitions": [
            {"id": "field-region", "mall_id": "mall-1", "key": "region", "label": "Región", "data_type": "select", "widget_type": "select", "required": True, "active": True, "sort_order": 1, "parent_field_id": None},
            {"id": "field-city", "mall_id": "mall-1", "key": "city", "label": "Ciudad", "data_type": "select", "widget_type": "drilldown", "required": False, "active": True, "sort_order": 2, "parent_field_id": "field-region"},
            {"id": "field-opening", "mall_id": "mall-1", "key": "opening_date", "label": "Apertura", "data_type": "date", "widget_type": "textbox", "required": False, "active": True, "sort_order": 3, "parent_field_id": None},
        ],
        "local_custom_field_options": [
            {"id": "opt-north", "field_definition_id": "field-region", "label": "Norte", "value": "north", "sort_order": 0, "active": True, "parent_option_id": None},
            {"id": "opt-south", "field_definition_id": "field-region", "label": "Sur", "value": "south", "sort_order": 1, "active": True, "parent_option_id": None},
            {"id": "opt-santiago", "field_definition_id": "field-city", "label": "Santiago", "value": "santiago", "sort_order": 0, "active": True, "parent_option_id": "opt-north"},
            {"id": "opt-punta", "field_definition_id": "field-city", "label": "Punta Cana", "value": "punta_cana", "sort_order": 1, "active": True, "parent_option_id": "opt-south"},
        ],
        "local_custom_field_values": [
            {"id": "val-1", "local_id": "local-a", "field_definition_id": "field-region", "selected_option_id": "opt-north", "value_text": None, "value_number": None, "value_date": None},
            {"id": "val-2", "local_id": "local-a", "field_definition_id": "field-city", "selected_option_id": "opt-santiago", "value_text": None, "value_number": None, "value_date": None},
            {"id": "val-3", "local_id": "local-b", "field_definition_id": "field-region", "selected_option_id": "opt-south", "value_text": None, "value_number": None, "value_date": None},
        ],
    })
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None)
    return LocalCustomFieldsService(fake_db, logger), fake_db


@pytest.mark.parametrize("data_type,widget_type,options", [
    ("text", "textbox", []),
    ("number", "textbox", []),
    ("date", "textbox", []),
    ("select", "select", [{"label": "Opción A", "value": "a"}]),
    ("select", "drilldown", [{"label": "Opción hija", "value": "child", "parent_option_id": "opt-north"}]),
])
def test_create_definition_with_unused_key_and_empty_maybe_single(data_type, widget_type, options):
    service, db = _service()
    result = service.create_definition(
        {"mall_id": "mall-1", "key": "nuevo_campo", "label": "Nuevo campo",
         "data_type": data_type, "widget_type": widget_type, "options": options,
         "parent_field_id": "field-region" if widget_type == "drilldown" else None},
        operator_ctx={"role": "it", "allowed_malls": ["mall-1"]},
        ensure_operator_can_access_mall=_guard,
    )
    assert result["key"] == "nuevo_campo"
    assert len(result["options"]) == len(options)
    assert len([row for row in db.tables["local_custom_field_definitions"] if row["key"] == "nuevo_campo"]) == 1


def test_create_definition_duplicate_key_still_returns_conflict():
    service, db = _service()
    before = len(db.tables["local_custom_field_definitions"])
    with pytest.raises(HTTPException) as error:
        service.create_definition(
            {"mall_id": "mall-1", "key": "region", "label": "Duplicado",
             "data_type": "text", "widget_type": "textbox"},
            operator_ctx={"role": "admin"}, ensure_operator_can_access_mall=_guard,
        )
    assert error.value.status_code == 409
    assert len(db.tables["local_custom_field_definitions"]) == before


@pytest.mark.parametrize("loader", ["_load_definition", "_load_local"])
def test_missing_record_returns_404_not_attribute_error(loader):
    service, _ = _service()
    with pytest.raises(HTTPException) as error:
        getattr(service, loader)("missing-id")
    assert error.value.status_code == 404


def test_update_definition_keeps_own_key():
    service, _ = _service()
    result = service.update_definition(
        "field-opening", {"label": "Nueva etiqueta"},
        operator_ctx={"role": "admin"}, ensure_operator_can_access_mall=_guard,
    )
    assert result["key"] == "opening_date"
    assert result["label"] == "Nueva etiqueta"


def test_create_definition_does_not_write_to_unauthorized_mall():
    service, db = _service()
    before = len(db.tables["local_custom_field_definitions"])
    with pytest.raises(HTTPException) as error:
        service.create_definition(
            {"mall_id": "mall-2", "key": "nuevo", "label": "Nuevo", "data_type": "text", "widget_type": "textbox"},
            operator_ctx={"role": "it", "allowed_malls": ["mall-1"]}, ensure_operator_can_access_mall=_guard,
        )
    assert error.value.status_code == 403
    assert len(db.tables["local_custom_field_definitions"]) == before


def test_create_endpoint_returns_json_and_cors_instead_of_unhandled_error(monkeypatch):
    for name in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.setenv(name, "")
    import main

    service, _ = _service()
    monkeypatch.setattr(main, "_local_custom_fields_service", lambda: service)
    monkeypatch.setattr(main, "_ensure_operator_can_access_mall", _guard)
    monkeypatch.setitem(main.app.dependency_overrides, main.require_it_or_admin_access,
                        lambda: {"role": "it", "allowed_malls": ["mall-1"]})

    async def run():
        transport = httpx.ASGITransport(app=main.app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            payload = {"mall_id": "mall-1", "key": "nuevo", "label": "Nuevo", "data_type": "text", "widget_type": "textbox"}
            headers = {"Origin": "https://msmall.vercel.app"}
            created = await client.post("/api/v1/locales/custom-fields", json=payload, headers=headers)
            assert created.status_code == 200, created.text
            assert created.json()["key"] == "nuevo"
            assert created.headers["access-control-allow-origin"] == headers["Origin"]
            duplicate = await client.post("/api/v1/locales/custom-fields", json=payload, headers=headers)
            assert duplicate.status_code == 409
            assert "Ya existe" in duplicate.json()["detail"]

    asyncio.run(run())


def test_upsert_local_values_validates_required_and_drilldown():
    service, _fake_db = _service()

    with pytest.raises(HTTPException) as required_exc:
        service.upsert_local_values(
            "local-c",
            [{"field_definition_id": "field-opening", "value_date": "2026-01-01"}],
            operator_ctx={"role": "it", "allowed_malls": ["mall-1"]},
            ensure_operator_can_access_mall=_guard,
        )
    assert required_exc.value.status_code == 400
    assert "Región" in required_exc.value.detail

    with pytest.raises(HTTPException) as drilldown_exc:
        service.upsert_local_values(
            "local-c",
            [
                {"field_definition_id": "field-region", "selected_option_id": "opt-north"},
                {"field_definition_id": "field-city", "selected_option_id": "opt-punta"},
            ],
            operator_ctx={"role": "it", "allowed_malls": ["mall-1"]},
            ensure_operator_can_access_mall=_guard,
        )
    assert drilldown_exc.value.status_code == 400
    assert "campo padre" in drilldown_exc.value.detail


def test_snapshot_filter_and_hierarchical_cube():
    service, _fake_db = _service()
    snapshot = service.build_snapshot("mall-1", ["local-a", "local-b", "local-c"], include_inactive=False)
    filtered = service.filter_local_ids_by_custom_filters(
        ["local-a", "local-b", "local-c"],
        snapshot,
        {"region": "north"},
    )
    assert filtered == ["local-a"]

    df = pd.DataFrame([
        {"id": "sale-1", "local_id": "local-a", "local_nombre": "Zara", "fecha": "2026-04-01", "total_neto": 100, "total_bruto": 118},
        {"id": "sale-2", "local_id": "local-b", "local_nombre": "Mango", "fecha": "2026-04-01", "total_neto": 200, "total_bruto": 236},
        {"id": "sale-3", "local_id": "local-c", "local_nombre": "Pull&Bear", "fecha": "2026-04-01", "total_neto": 50, "total_bruto": 59},
    ])

    cube = service.build_cube_response(
        df,
        grouping="DIA",
        metric="total_neto",
        start_date="2026-04-01",
        end_date="2026-04-01",
        snapshot=snapshot,
        custom_dimension_key="region",
    )

    assert cube["hierarchical"] is True
    assert cube["row_label"] == "Región"
    assert cube["columns"][0] == "row_label"
    labels = [row["row_label"] for row in cube["data"]]
    assert "Norte" in labels
    assert "Sur" in labels
    assert EMPTY_GROUP_LABEL in labels
    north_group = next(row for row in cube["data"] if row["row_label"] == "Norte")
    assert north_group["01/04"] == 100
    assert next(row for row in cube["data"] if row["row_label"] == "  Zara")["01/04"] == 100


def test_cube_sums_preaggregated_transaction_counts():
    service, _fake_db = _service()
    snapshot = service.build_snapshot("mall-1", ["local-a"], include_inactive=False)
    df = pd.DataFrame([
        {
            "local_id": "local-a",
            "local_nombre": "Zara",
            "fecha": "2026-08-01",
            "total_neto": 100,
            "total_bruto": 118,
            "transacciones": 3,
        },
        {
            "local_id": "local-a",
            "local_nombre": "Zara",
            "fecha": "2026-08-02",
            "total_neto": 200,
            "total_bruto": 236,
            "transacciones": 4,
        },
    ])

    cube = service.build_cube_response(
        df,
        grouping="MES",
        metric="transacciones",
        start_date="2026-08-01",
        end_date="2026-08-31",
        snapshot=snapshot,
    )

    assert cube["data"][0]["2026-08"] == 7
    assert cube["data"][0]["TOTAL_FILA"] == 7

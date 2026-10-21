import asyncio
import csv
import io
import re
from types import SimpleNamespace

import pytest
import httpx

from services.import_backup_service import CSV_COLUMNS, ImportBackupService, InvalidBackupSelection


MALL = "10000000-0000-0000-0000-000000000001"
OTHER_MALL = "10000000-0000-0000-0000-000000000002"
LOCAL = "20000000-0000-0000-0000-000000000001"
INACTIVE = "20000000-0000-0000-0000-000000000002"
FOREIGN = "20000000-0000-0000-0000-000000000003"


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def request(self, method, path, **kwargs):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://testserver") as client:
                return await client.request(method, path, **kwargs)
        return asyncio.run(run())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


class Query:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self.filters, self.orders = [], []
        self.size = 1000
        self.payload = None

    def select(self, fields):
        self.fields = fields
        return self

    def eq(self, field, value):
        self.filters.append(("eq", field, value))
        return self

    def in_(self, field, values):
        self.filters.append(("in", field, values))
        return self

    def gte(self, field, value):
        self.filters.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self.filters.append(("lte", field, value))
        return self

    def gt(self, field, value):
        self.filters.append(("gt", field, value))
        return self

    def or_(self, expression):
        match = re.fullmatch(r"fecha\.gt\.([^,]+),and\(fecha\.eq\.([^,]+),id\.gt\.([^)]+)\)", expression)
        assert match and match[1] == match[2]
        self.filters.append(("cursor", "fecha", (match[1], match[3])))
        return self

    def order(self, field):
        self.orders.append(field)
        return self

    def limit(self, size):
        self.size = size
        return self

    def insert(self, payload):
        self.payload = payload
        return self

    def execute(self):
        self.db.queries.append(self)
        if self.payload is not None:
            self.db.writes.append((self.table, self.payload))
            return SimpleNamespace(data=[self.payload])
        if self.db.fail_late and self.table == "ventas" and any(item[0] == "cursor" for item in self.filters):
            raise RuntimeError("Simulated database failure")
        rows = self.db.rows.get(self.table, [])
        for op, field, value in self.filters:
            if op == "eq":
                rows = [row for row in rows if row.get(field) == value]
            elif op == "in":
                rows = [row for row in rows if row.get(field) in value]
            elif op == "gte":
                rows = [row for row in rows if row[field] >= value]
            elif op == "lte":
                rows = [row for row in rows if row[field] <= value]
            elif op == "gt":
                rows = [row for row in rows if row[field] > value]
            elif op == "cursor":
                rows = [row for row in rows if (row["fecha"], row["id"]) > value]
        return SimpleNamespace(data=sorted(rows, key=lambda row: tuple(row[key] for key in self.orders))[:self.size])


class Database:
    def __init__(self, sales=None):
        self.queries, self.writes = [], []
        self.fail_late = False
        self.rows = {
            "locales": [
                {"id": LOCAL, "mall_id": MALL, "nombre": "Café, Norte", "codigo_interno": "001", "activo": True},
                {"id": INACTIVE, "mall_id": MALL, "nombre": "Árbol", "codigo_interno": "002", "activo": False},
                {"id": FOREIGN, "mall_id": OTHER_MALL, "nombre": "Otro Mall", "codigo_interno": "001", "activo": True},
            ],
            "malls": [{"id": MALL, "nombre": "Mall de prueba"}],
            "ventas": sales or [],
            "logs_carga": [],
        }

    def table(self, name):
        return Query(self, name)


def sale(number=1, **overrides):
    return {"id": f"30000000-0000-0000-0000-{number:012d}", "local_id": LOCAL, "fecha": "2026-01-01",
            "hora_transaccion": "10:15:00", "factura_no": "00123", "total_bruto": "118.00",
            "total_impuestos": "18.00", "total_neto": "100.00", "created_at": "2026-02-10T14:00:00+00:00",
            "metadata": {}, **overrides}


def read_backup(db, local_ids=None, start="2026-01-01", end="2026-01-31"):
    backup = ImportBackupService(db).generate(MALL, start, end, local_ids)
    with backup.file:
        raw = backup.file.read()
    assert raw.startswith(b"\xef\xbb\xbf")
    return backup, list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))


def test_backup_preserves_amounts_and_sale_dates_includes_inactive_and_excludes_other_malls():
    db = Database([sale(), sale(2, fecha="2026-01-31", local_id=INACTIVE),
                   sale(3, fecha="2025-12-31"), sale(4, fecha="2026-02-01"), sale(5, local_id=FOREIGN)])
    backup, rows = read_backup(db)
    assert backup.records == 2
    assert set(rows[0]) == set(CSV_COLUMNS)
    assert rows[0]["fecha_venta"] == "2026-01-01"
    assert rows[0]["fecha_creacion_registro"] == "2026-02-10T14:00:00+00:00"
    assert [rows[0][key] for key in ("total_bruto", "total_impuestos", "total_neto")] == ["118.00", "18.00", "100.00"]
    assert rows[0]["local_nombre"] == "Café, Norte"
    assert rows[0]["codigo_local"] == "001"
    assert rows[0]["numero_transaccion"] == "00123"
    assert rows[0]["tipo_registro"] == rows[0]["fecha_importacion"] == rows[0]["archivo_origen"] == ""
    assert rows[1]["local_id"] == INACTIVE


def test_selected_store_and_single_day_filter_and_unknown_values():
    db = Database([sale(), sale(2, local_id=INACTIVE, total_bruto="-12.50", total_impuestos=0, total_neto=None)])
    backup, rows = read_backup(db, [INACTIVE], end="2026-01-01")
    assert backup.records == 1
    assert rows[0]["total_bruto"] == "-12.50"
    assert rows[0]["total_impuestos"] == "0"
    assert rows[0]["total_neto"] == ""


@pytest.mark.parametrize("selection", [[], [FOREIGN], [LOCAL, FOREIGN]])
def test_rejects_empty_and_foreign_selections_before_reading_sales(selection):
    db = Database([sale()])
    with pytest.raises(InvalidBackupSelection):
        ImportBackupService(db).generate(MALL, "2026-01-01", "2026-01-31", selection)
    assert not any(query.table == "ventas" for query in db.queries)


def test_paginates_sales_beyond_1000_without_duplicates_or_truncation():
    db = Database([sale(index) for index in range(1, 2002)])
    backup, rows = read_backup(db)
    assert backup.records == 2001
    assert len({row["id_registro"] for row in rows}) == 2001
    assert len([query for query in db.queries if query.table == "ventas"]) == 3


def test_store_list_is_paginated_and_does_not_expose_connection_credentials():
    db = Database()
    db.rows["locales"] = [{"id": f"{index:036d}", "mall_id": MALL, "nombre": str(index)} for index in range(1001)]
    assert len(ImportBackupService(db).list_stores(MALL)) == 1001
    assert all(query.fields == "id,codigo_interno,nombre,activo" for query in db.queries)


def test_store_ids_are_batched_for_large_malls():
    db = Database()
    db.rows["locales"] = [{"id": f"{index:036d}", "mall_id": MALL, "nombre": str(index)} for index in range(201)]
    db.rows["ventas"] = [sale(index + 1, local_id=store["id"]) for index, store in enumerate(db.rows["locales"])]
    backup, rows = read_backup(db)
    assert backup.records == len(rows) == 201
    assert all(len(values) <= 100 for query in db.queries if query.table == "ventas"
               for op, field, values in query.filters if op == "in" and field == "local_id")


def test_trace_requires_same_mall_local_and_batch_and_ignores_failed_attempts():
    db = Database([sale(metadata={"batch_id": "batch-1", "granularity": "daily"})])
    log = {"id": "log-1", "mall_id": MALL, "local_id": LOCAL, "batch_id": "batch-1",
           "fecha_hora": "2026-02-10T14:05:00+00:00", "archivo": "ventas.csv", "canal": "SFTP", "estado": "exito"}
    db.rows["logs_carga"] = [log, {**log, "id": "log-2", "local_id": INACTIVE, "archivo": "wrong.csv"},
                             {**log, "id": "log-3", "mall_id": OTHER_MALL, "archivo": "foreign.csv"},
                             {**log, "id": "log-4", "estado": "error", "archivo": "failed.csv", "fecha_hora": "2026-03-01"}]
    _, rows = read_backup(db)
    assert rows[0]["tipo_registro"] == "resumen_diario"
    assert rows[0]["archivo_origen"] == "ventas.csv"
    assert rows[0]["fecha_importacion"] == log["fecha_hora"]
    assert rows[0]["canal_importacion"] == "SFTP"


def test_csv_escapes_formulas_quotes_unicode_and_embedded_newlines():
    db = Database([sale(factura_no='=HYPERLINK("evil")')])
    db.rows["locales"][0]["nombre"] = 'Café, "Norte"\nPiso 1'
    _, rows = read_backup(db)
    assert rows[0]["numero_transaccion"] == '\'=HYPERLINK("evil")'
    assert rows[0]["local_nombre"] == 'Café, "Norte"\nPiso 1'


def test_empty_period_is_a_valid_header_only_csv():
    backup, rows = read_backup(Database())
    assert backup.records == 0 and rows == []


@pytest.fixture
def api(monkeypatch):
    import main
    db = Database([sale()])
    access = {"role": "custom_auditor", "user_id": "user-1", "permissions": {"import_backup": {"view": True}}}

    async def get_access(_user_id):
        return access

    monkeypatch.setattr(main, "supabase", db)
    monkeypatch.setattr(main, "_get_access_context", get_access)
    monkeypatch.setattr(main, "_get_user_mall_ids", lambda _: [MALL])
    # Existing CSV regressions isolate accounting; shared-DB quota behavior has
    # its own PostgreSQL integration suite.
    class Lease:
        request_id = "test-request"
        max_bytes = 50_000_000
        start = check = lambda self: None
        progress = prepare = lambda self, size: None
        close = lambda self, failed=False: None

    monkeypatch.setattr(main, "ImportBackupQuotaService", lambda *_: SimpleNamespace(reserve=lambda days: Lease()))
    previous = main.app.dependency_overrides.copy()
    main.app.dependency_overrides[main.get_current_user_id] = lambda: "user-1"
    try:
        yield SimpleNamespace(client=ASGIClient(main.app), db=db, access=access, main=main)
    finally:
        main.app.dependency_overrides = previous


def request_csv(api, **overrides):
    return api.client.post("/api/v1/export/import-backup/csv", headers={"X-Mall-Id": MALL},
                           json={"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31", **overrides})


def test_authenticated_api_downloads_csv_and_audits_generation(api):
    response = request_csv(api, local_ids=[LOCAL])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "no-store"
    assert int(response.headers["content-length"]) == len(response.content)
    assert response.headers["x-backup-records"] == "1"
    assert response.headers["content-disposition"].endswith('2026-01-01_2026-01-31.csv"')
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 1 and rows[0]["local_id"] == LOCAL
    assert api.db.writes[0][1]["accion"] == "backup_importaciones_generado"
    assert api.db.writes[0][1]["metadata"]["records"] == 1


@pytest.mark.parametrize("path", ["/stores", "/csv"])
def test_api_requires_permission_and_mall_membership_for_both_routes(api, path):
    def call(mall):
        return api.client.request("GET" if path == "/stores" else "POST", "/api/v1/export/import-backup" + path,
                                  headers={"X-Mall-Id": mall},
                                  **({"json": {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"}} if path == "/csv" else {}))
    assert call(OTHER_MALL).status_code == 403
    api.access["permissions"]["import_backup"]["view"] = False
    assert call(MALL).status_code == 403
    assert api.db.queries == []


@pytest.mark.parametrize("body,status", [
    ({"fecha_inicio": "2026-02-01"}, 400), ({"fecha_fin": "bad-date"}, 422),
    ({"local_ids": []}, 400), ({"local_ids": [FOREIGN]}, 400), ({"local_ids": ["invalid"]}, 422),
])
def test_api_rejects_invalid_dates_and_store_selection(api, body, status):
    assert request_csv(api, **body).status_code == status
    assert api.db.writes == []


def test_late_database_error_never_returns_a_partial_successful_csv(api, monkeypatch):
    import services.import_backup_service as service
    original = service.SpooledTemporaryFile
    opened = []

    def track_file(**kwargs):
        file = original(**kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(service, "SpooledTemporaryFile", track_file)
    api.db.rows["ventas"] = [sale(index) for index in range(1, 1002)]
    api.db.fail_late = True
    response = request_csv(api)
    assert response.status_code == 500
    assert "text/csv" not in response.headers["content-type"]
    assert opened[0].closed
    assert api.db.writes == []


def test_new_routes_reject_missing_authentication():
    import main
    client = ASGIClient(main.app)
    assert client.get("/api/v1/export/import-backup/stores", headers={"X-Mall-Id": MALL}).status_code in {401, 403}


def test_sales_report_permission_does_not_grant_backup_access(api):
    api.access["permissions"] = {"sales_reports": {"view": True}}
    assert request_csv(api).status_code == 403
    assert not api.db.writes


@pytest.mark.parametrize("method,path", [("GET", "quota"), ("GET", "stores"), ("POST", "csv")])
def test_backup_routes_require_independent_permission(api, method, path):
    api.access["permissions"] = {"sales_reports": {"view": True}, "import_backup": {"view": False}}
    response = api.client.request(method, "/api/v1/export/import-backup/" + path,
        headers={"X-Mall-Id": MALL}, json={"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-31"})
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_settings_require_settings_permission_not_download_permission(api, method):
    response = api.client.request(method, "/api/v1/export/import-backup/settings",
        headers={"X-Mall-Id": MALL}, json={})
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_admin_settings_work_without_backup_download_permission(api, monkeypatch, method):
    api.access.update(role="admin", has_role_assignment=True, permissions={"backup_settings": {"view": True, "update": True}})
    calls = []
    monkeypatch.setattr(api.main, "ImportBackupQuotaService", lambda *_: SimpleNamespace(
        status=lambda: {"limits": {}}, configure=lambda policy: calls.append(policy) or {"limits": {}}))
    response = api.client.request(method, "/api/v1/export/import-backup/settings",
        headers={"X-Mall-Id": MALL}, json={})
    assert response.status_code == 200
    assert response.json()["can_configure"] is True
    assert response.headers["cache-control"] == "no-store"
    assert len(calls) == (method == "PUT")


@pytest.mark.parametrize("role", ["custom_limits", "admin"])
@pytest.mark.parametrize("view,update,method,expected", [
    (False,False,"GET",403), (False,False,"PUT",403),
    (True,False,"GET",200), (True,False,"PUT",403),
    (True,True,"GET",200), (True,True,"PUT",200),
    (False,True,"GET",403), (False,True,"PUT",403),
])
def test_global_settings_permissions_are_authoritative(api, monkeypatch, role, view, update, method, expected):
    api.access.update(role=role, has_role_assignment=True, permissions={"backup_settings": {"view": view,"update": update}})
    writes = []
    monkeypatch.setattr(api.main, "ImportBackupQuotaService", lambda *_: SimpleNamespace(
        status=lambda: {}, configure=lambda policy: writes.append(policy) or {}))
    response = api.client.request(method,"/api/v1/export/import-backup/settings", headers={"X-Mall-Id":MALL}, json={})
    assert response.status_code == expected
    assert len(writes) == (method == "PUT" and expected == 200)
    if expected == 200:
        assert response.json()["can_configure"] == (view and update)


@pytest.mark.parametrize("method", ["GET", "PUT"])
def test_delegating_global_settings_does_not_grant_cross_mall_access(api, method):
    api.access.update(has_role_assignment=True, permissions={"backup_settings": {"view": True,"update": True}})
    response = api.client.request(method,"/api/v1/export/import-backup/settings",headers={"X-Mall-Id":OTHER_MALL},json={})
    assert response.status_code == 403
    assert not api.db.writes


def test_settings_permission_does_not_grant_download_permission(api):
    api.access.update(has_role_assignment=True, permissions={"backup_settings": {"view": True,"update": True}})
    assert request_csv(api).status_code == 403

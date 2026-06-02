import asyncio
import importlib
import sys
from types import SimpleNamespace


def _load_main(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # type: ignore
    return importlib.reload(main)


class _FakeTableQuery:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self._filters = []
        self._order = None
        self._range = None
        self._limit = None
        self._payload = None
        self._mode = "select"

    def select(self, *_args, **_kwargs):
        self._mode = "select"
        return self

    def eq(self, key, value):
        self._filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self._filters.append(("in", key, list(values)))
        return self

    def gte(self, key, value):
        self._filters.append(("gte", key, value))
        return self

    def lte(self, key, value):
        self._filters.append(("lte", key, value))
        return self

    def order(self, key):
        self._order = key
        return self

    def range(self, start, end):
        self._range = (int(start), int(end))
        return self

    def limit(self, value):
        self._limit = int(value)
        return self

    def upsert(self, payload, **_kwargs):
        self._mode = "upsert"
        self._payload = payload
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def _apply_filters(self, rows):
        result = list(rows)
        for op, key, value in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(key) == value]
            elif op == "in":
                result = [r for r in result if r.get(key) in value]
            elif op == "gte":
                result = [r for r in result if r.get(key) >= value]
            elif op == "lte":
                result = [r for r in result if r.get(key) <= value]
        return result

    def execute(self):
        rows = self.supabase.tables.setdefault(self.table_name, [])

        if self._mode == "select":
            data = self._apply_filters(rows)
            if self._order:
                data = sorted(data, key=lambda row: row.get(self._order))
            if self._range is not None:
                start, end = self._range
                data = data[start : end + 1]
            if self._limit is not None:
                data = data[: self._limit]
            return SimpleNamespace(data=[dict(row) for row in data])

        if self._mode == "upsert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            for payload in payloads:
                row = dict(payload)
                rows.append(row)
                self.supabase.upserts.append(row)
            return SimpleNamespace(data=[dict(row) for row in payloads])

        if self._mode == "insert":
            payloads = self._payload if isinstance(self._payload, list) else [self._payload]
            for payload in payloads:
                row = dict(payload)
                rows.append(row)
            return SimpleNamespace(data=[dict(row) for row in payloads])

        if self._mode == "update":
            filtered = self._apply_filters(rows)
            for row in filtered:
                row.update(dict(self._payload or {}))
            return SimpleNamespace(data=[dict(row) for row in filtered])

        return SimpleNamespace(data=[])


class _FakeSupabase:
    def __init__(self, tables):
        self.tables = tables
        self.upserts = []

    def table(self, table_name):
        return _FakeTableQuery(self, table_name)


def test_process_file_content_rejects_blank_local_code(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "L001", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "factura_numero,fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto",
        "1001,2026-03-01,,100,18,82",
    ])
    config = {
        "tipo_archivo": "CSV",
        "mapping": {
            "factura_numero": "factura_numero",
            "fecha_venta": "fecha_venta",
            "local_codigo": "local_codigo",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
    }

    count, errors = main.process_file_content(content, "ventas.csv", config, "batch-1", "mall-1")

    assert count == 0
    assert fake_db.upserts == []
    assert errors == [{
        "linea": 2,
        "error": "Falta local_codigo. No se puede cargar una venta sin un código de local válido."
    }]


def test_process_file_content_inserts_rows_with_valid_local_code(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "L001", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "factura_numero,fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto",
        "1001,2026-03-01,L001,100,18,82",
    ])
    config = {
        "tipo_archivo": "CSV",
        "mapping": {
            "factura_numero": "factura_numero",
            "fecha_venta": "fecha_venta",
            "local_codigo": "local_codigo",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
    }

    count, errors = main.process_file_content(content, "ventas.csv", config, "batch-1", "mall-1")

    assert count == 1
    assert errors == []
    assert fake_db.upserts == [{
        "factura_no": "1001",
        "fecha": "2026-03-01",
        "total_bruto": 100.0,
        "total_impuestos": 18.0,
        "total_neto": 82.0,
        "local_id": "local-1",
        "mall_id": "mall-1",
    }]


def test_process_file_content_rejects_rows_in_closed_import_period(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "L001", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "factura_numero,fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto",
        "1001,2026-05-31,L001,100,18,82",
        "1002,2026-06-01,L001,200,36,164",
    ])
    config = {
        "tipo_archivo": "CSV",
        "fecha_corte_importacion": "2026-05-31",
        "mapping": {
            "factura_numero": "factura_numero",
            "fecha_venta": "fecha_venta",
            "local_codigo": "local_codigo",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
    }

    count, errors = main.process_file_content(content, "ventas.csv", config, "batch-1", "mall-1")

    assert count == 1
    assert len(errors) == 1
    assert errors[0]["linea"] == 2
    assert "periodo cerrado" in errors[0]["error"]
    assert fake_db.upserts[0]["factura_no"] == "1002"
    assert fake_db.upserts[0]["fecha"] == "2026-06-01"


def test_process_file_content_parses_comma_decimal_mapping(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "L001", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "Id_NumeroOperacion\tNCF\tFECHA\tHORA\tTOTALBRUTO\tTOTALIMPUESTOS\tTOTALNETO\tLOCAL",
        "13718\tE320000378096\t1/05/2026\t15:57\t3,385,593,220\t609,406,780\t3995,00\tL001",
    ])
    config = {
        "tipo_archivo": "TXT",
        "mapping": {
            "factura_numero": "NCF",
            "fecha_venta": "FECHA",
            "local_codigo": "LOCAL",
            "total_bruto": "TOTALNETO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALBRUTO",
            "hora_transaccion": "HORA",
        },
        "constants": {
            "_date_format": "DD/MM/YYYY",
            "_decimal_separator": ",",
        },
    }

    count, errors = main.process_file_content(content, "ventas.txt", config, "batch-1", "mall-1")

    assert count == 1
    assert errors == []
    row = fake_db.upserts[0]
    assert row["factura_no"] == "E320000378096"
    assert row["fecha"] == "2026-05-01"
    assert row["total_bruto"] == 3995.0
    assert row["total_impuestos"] == 609.40678
    assert row["total_neto"] == 3385.59322
    assert row["hora_transaccion"] == "15:57:00"


def test_process_file_content_generates_invoice_sequence(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "PABT-01", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto",
        "2026-03-01,PABT-01,100,18,82",
        "2026-03-01,PABT-01,200,36,164",
    ])
    config = {
        "tipo_archivo": "CSV",
        "mapping": {
            "fecha_venta": "fecha_venta",
            "local_codigo": "local_codigo",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
        "constants": {
            "_factura_numero_mode": "generated_sequence",
        },
    }

    count, errors = main.process_file_content(content, "ventas.csv", config, "batch-1", "mall-1")

    assert count == 2
    assert errors == []
    assert [row["factura_no"] for row in fake_db.upserts] == [
        "PABT01202603010001",
        "PABT01202603010002",
    ]


def test_process_file_content_concatenates_invoice_fields(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {"id": "local-1", "codigo_interno": "PABT-01", "mall_id": "mall-1"},
        ],
        "ventas": [],
    })
    monkeypatch.setattr(main, "supabase", fake_db)

    content = "\n".join([
        "fecha_venta,local_codigo,total_bruto,total_impuestos,total_neto",
        "01/03/2026,PABT-01,100,18,82",
    ])
    config = {
        "tipo_archivo": "CSV",
        "mapping": {
            "fecha_venta": "fecha_venta",
            "local_codigo": "local_codigo",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
        "constants": {
            "_date_format": "DD/MM/YYYY",
            "_factura_numero_mode": "concat",
            "_factura_numero_concat_fields": "local_codigo,fecha_venta,numero_registro",
            "_factura_numero_concat_separator": "",
        },
    }

    count, errors = main.process_file_content(content, "ventas.csv", config, "batch-1", "mall-1")

    assert count == 1
    assert errors == []
    assert fake_db.upserts[0]["factura_no"] == "PABT01202603010001"


def test_dashboard_ignores_orphan_sales_rows(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {
                "id": "local-1",
                "nombre": "Tienda Valida",
                "mall_id": "mall-1",
                "tipo_negocio": "Moda",
                "rubro": "Ropa",
            },
        ],
        "ventas": [
            {
                "local_id": "local-1",
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 100,
                "total_neto": 82,
            },
            {
                "local_id": None,
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 900,
                "total_neto": 738,
            },
            {
                "local_id": "ghost-local",
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 450,
                "total_neto": 369,
            },
        ],
    })
    monkeypatch.setattr(main, "supabase", fake_db)
    monkeypatch.setattr(main, "_cache_get", lambda _key: main._CACHE_MISS)
    monkeypatch.setattr(main, "_cache_set", lambda *_args, **_kwargs: None)

    result = asyncio.run(main.get_dashboard_data("2026-03-01", "2026-03-01", "mall-1"))

    assert result["ventas_totales_bruto"] == 100
    assert result["ventas_totales_neto"] == 82
    assert result["transacciones"] == 1
    assert result["top_locales"] == [{"name": "Tienda Valida", "total": 100.0}]
    assert result["ventas_por_tienda_completo"] == {"Tienda Valida": 100.0}
    assert result["ventas_por_tipo_negocio"] == [{"name": "Moda", "value": 100.0}]
    assert result["ventas_por_rubro"] == [{"name": "Ropa", "value": 100.0}]
    assert result["ventas_por_tipo_negocio_top_locales"]["Moda"] == [{
        "name": "Tienda Valida",
        "total": 100.0,
        "total_neto": 82.0,
        "transacciones": 1,
        "ticket_promedio": 100.0,
        "participacion": 100.0,
    }]
    assert result["ventas_por_rubro_top_locales"]["Ropa"] == [{
        "name": "Tienda Valida",
        "total": 100.0,
        "total_neto": 82.0,
        "transacciones": 1,
        "ticket_promedio": 100.0,
        "participacion": 100.0,
    }]


def test_dashboard_groups_sales_by_business_type_and_rubro(monkeypatch):
    main = _load_main(monkeypatch)
    fake_db = _FakeSupabase({
        "locales": [
            {
                "id": "local-1",
                "nombre": "Zapatos Norte",
                "mall_id": "mall-1",
                "tipo_negocio": "Calzado",
                "rubro": "Moda",
            },
            {
                "id": "local-2",
                "nombre": "Ropa Sur",
                "mall_id": "mall-1",
                "tipo_negocio": "Boutique",
                "rubro": "Moda",
            },
            {
                "id": "local-3",
                "nombre": "Cafe Central",
                "mall_id": "mall-1",
                "tipo_negocio": "",
                "rubro": None,
            },
        ],
        "ventas": [
            {
                "local_id": "local-1",
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 100,
                "total_neto": 82,
            },
            {
                "local_id": "local-1",
                "mall_id": "mall-1",
                "fecha": "2026-03-02",
                "total_bruto": 50,
                "total_neto": 41,
            },
            {
                "local_id": "local-2",
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 300,
                "total_neto": 246,
            },
            {
                "local_id": "local-3",
                "mall_id": "mall-1",
                "fecha": "2026-03-01",
                "total_bruto": 25,
                "total_neto": 20.5,
            },
        ],
    })
    monkeypatch.setattr(main, "supabase", fake_db)
    monkeypatch.setattr(main, "_cache_get", lambda _key: main._CACHE_MISS)
    monkeypatch.setattr(main, "_cache_set", lambda *_args, **_kwargs: None)

    result = asyncio.run(main.get_dashboard_data("2026-03-01", "2026-03-31", "mall-1"))

    assert result["ventas_por_tipo_negocio"] == [
        {"name": "Boutique", "value": 300.0},
        {"name": "Calzado", "value": 150.0},
        {"name": "Sin tipo de negocio", "value": 25.0},
    ]
    assert result["ventas_por_rubro"] == [
        {"name": "Moda", "value": 450.0},
        {"name": "Sin rubro", "value": 25.0},
    ]
    assert result["ventas_por_tipo_negocio_top_locales"]["Calzado"] == [{
        "name": "Zapatos Norte",
        "total": 150.0,
        "total_neto": 123.0,
        "transacciones": 2,
        "ticket_promedio": 75.0,
        "participacion": 100.0,
    }]
    assert result["ventas_por_rubro_top_locales"]["Moda"] == [
        {
            "name": "Ropa Sur",
            "total": 300.0,
            "total_neto": 246.0,
            "transacciones": 1,
            "ticket_promedio": 300.0,
            "participacion": 300.0 / 450.0 * 100,
        },
        {
            "name": "Zapatos Norte",
            "total": 150.0,
            "total_neto": 123.0,
            "transacciones": 2,
            "ticket_promedio": 75.0,
            "participacion": 150.0 / 450.0 * 100,
        },
    ]

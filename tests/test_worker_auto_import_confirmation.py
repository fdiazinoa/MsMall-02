import importlib
import io
import stat as stat_module
import sys
from types import SimpleNamespace


def _load_worker(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if "worker_importacion" in sys.modules:
        del sys.modules["worker_importacion"]
    import worker_importacion  # type: ignore
    return importlib.reload(worker_importacion)


class _FakeFile:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


class _FakeSFTP:
    def __init__(self, files):
        self.files = dict(files)
        self.renames = []

    def stat(self, path):
        return SimpleNamespace(st_mode=stat_module.S_IFDIR)

    def listdir_attr(self, path):
        return [
            SimpleNamespace(
                filename=name,
                st_mode=stat_module.S_IFREG,
                st_mtime=1,
                st_size=len(content),
            )
            for name, content in self.files.items()
        ]

    def open(self, path, _mode):
        filename = path.split("/")[-1]
        return _FakeFile(self.files[filename])

    def rename(self, old_path, new_path):
        old_name = old_path.split("/")[-1]
        new_name = new_path.split("/")[-1]
        self.renames.append((old_name, new_name))
        self.files[new_name] = self.files.pop(old_name)

    def close(self):
        return None


class _FakeSSH:
    def close(self):
        return None


class _FakeWorkerTable:
    def __init__(self, supabase, table_name):
        self.supabase = supabase
        self.table_name = table_name
        self.payload = None
        self._select = None
        self._filters = []
        self._in_filters = []
        self._write_mode = None
        self._upsert_options = {}

    def select(self, value, *_args, **_kwargs):
        self._select = value
        return self

    def eq(self, column, value):
        self._filters.append((column, value))
        return self

    def in_(self, column, values):
        self._in_filters.append((column, set(values or [])))
        return self

    def insert(self, payload):
        self.payload = payload
        self._write_mode = "insert"
        return self

    def upsert(self, payload, **kwargs):
        self.payload = payload
        self._write_mode = "upsert"
        self._upsert_options = dict(kwargs)
        self.supabase.upsert_calls.append({
            "table": self.table_name,
            "payload": payload,
            **kwargs,
        })
        return self

    def execute(self):
        if self.payload is not None:
            rows = self.payload if isinstance(self.payload, list) else [self.payload]
            table_rows = self.supabase.tables.setdefault(self.table_name, [])
            if self._write_mode != "upsert":
                table_rows.extend([dict(row) for row in rows])
                return SimpleNamespace(data=rows)

            inserted = []
            conflict_columns = [
                column.strip()
                for column in str(self._upsert_options.get("on_conflict") or "").split(",")
                if column.strip()
            ]
            for row in rows:
                conflict = next(
                    (
                        existing
                        for existing in table_rows
                        if conflict_columns
                        and all(existing.get(column) == row.get(column) for column in conflict_columns)
                    ),
                    None,
                )
                if conflict is not None and self._upsert_options.get("ignore_duplicates"):
                    continue
                if conflict is not None:
                    conflict.update(dict(row))
                    inserted.append(dict(conflict))
                    continue
                table_rows.append(dict(row))
                inserted.append(dict(row))
            return SimpleNamespace(data=inserted)

        rows = list(self.supabase.tables.get(self.table_name, []))
        for column, value in self._filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self._in_filters:
            rows = [row for row in rows if row.get(column) in values]
        if self._select and self._select != "*":
            columns = [col.strip() for col in str(self._select).split(",")]
            rows = [{col: row.get(col) for col in columns} for row in rows]
        return SimpleNamespace(data=rows)


class _FakeWorkerSupabase:
    def __init__(self):
        self.tables = {}
        self.upsert_calls = []

    def table(self, table_name):
        return _FakeWorkerTable(self, table_name)


class _FakeLogQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class _FakeLogSupabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, table_name):
        assert table_name == "logs_carga"
        return _FakeLogQuery(self.rows)


def test_worker_normalizes_remote_host_with_protocol_and_path(monkeypatch):
    worker = _load_worker(monkeypatch)

    assert worker._normalize_remote_host("ftp://ftp.sambilftp.com/") == "ftp.sambilftp.com"
    assert worker._normalize_remote_host("sftp://www.example.com/inbox") == "www.example.com"
    assert worker._candidate_hosts("sftp://www.example.com/inbox") == ["www.example.com", "example.com"]


def test_worker_ftp_client_uses_normalized_host(monkeypatch):
    worker = _load_worker(monkeypatch)
    calls = []

    class FakeFTP:
        def connect(self, host, port, timeout=0):
            calls.append(("connect", host, port, timeout))

        def login(self, user, password):
            calls.append(("login", user, password))

        def set_pasv(self, enabled):
            calls.append(("set_pasv", enabled))

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(worker, "FTP", FakeFTP)

    worker.get_ftp_client("ftp://ftp.sambilftp.com/", 21, "demo", "secret")

    assert calls[0] == ("connect", "ftp.sambilftp.com", 21, 10)
    assert ("login", "demo", "secret") in calls
    assert ("set_pasv", True) in calls


def test_worker_process_file_logic_generates_invoice_sequence(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "fecha_venta,total_bruto,total_impuestos,total_neto",
        "2026-03-01,100,18,82",
        "2026-03-01,200,36,164",
    ])
    config = {
        "nombre": "PABT-01",
        "id": "local-1",
        "mall_id": "mall-1",
        "codigo_interno": "PABT-01",
        "file_type": "CSV",
        "mapping_config": {
            "fecha_venta": "fecha_venta",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
        "constants_config": {
            "_factura_numero_mode": "generated_sequence",
        },
    }

    count, errors, stats = worker.process_file_logic(config, "ventas.csv", content)

    assert count == 2
    assert errors == []
    assert stats["moving_window_mode"] is False
    assert [row["factura_no"] for row in fake_db.tables["ventas"]] == [
        "PABT01202603010001",
        "PABT01202603010002",
    ]


def test_worker_process_file_logic_rejects_closed_import_period(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "fecha_venta,total_bruto,total_impuestos,total_neto",
        "2026-05-31,100,18,82",
        "2026-06-01,200,36,164",
    ])
    config = {
        "nombre": "PABT-01",
        "id": "local-1",
        "mall_id": "mall-1",
        "codigo_interno": "PABT-01",
        "fecha_corte_importacion": "2026-05-31",
        "file_type": "CSV",
        "mapping_config": {
            "fecha_venta": "fecha_venta",
            "total_bruto": "total_bruto",
            "total_impuestos": "total_impuestos",
            "total_neto": "total_neto",
        },
        "constants_config": {
            "_factura_numero_mode": "generated_sequence",
        },
    }

    count, errors, _stats = worker.process_file_logic(config, "ventas.csv", content)

    assert count == 1
    assert len(errors) == 1
    assert errors[0]["linea"] == 2
    assert "periodo cerrado" in errors[0]["error"]
    assert fake_db.tables["ventas"][0]["factura_no"] == "PABT01202606010002"
    assert fake_db.tables["ventas"][0]["fecha"] == "2026-06-01"


def test_worker_process_file_logic_parses_comma_decimal_mapping(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "NCF\tFECHA\tHORA\tTOTALBRUTO\tTOTALIMPUESTOS\tTOTALNETO",
        "E320000378096\t1/05/2026\t15:57\t3,385,593,220\t609,406,780\t3995,00",
    ])
    config = {
        "nombre": "L001",
        "id": "local-1",
        "mall_id": "mall-1",
        "codigo_interno": "L001",
        "file_type": "TXT",
        "mapping_config": {
            "factura_numero": "NCF",
            "fecha_venta": "FECHA",
            "total_bruto": "TOTALNETO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALBRUTO",
        },
        "constants_config": {
            "_decimal_separator": ",",
        },
    }

    count, errors, _stats = worker.process_file_logic(config, "ventas.txt", content)

    assert count == 1
    assert errors == []
    row = fake_db.tables["ventas"][0]
    assert row["factura_no"] == "E320000378096"
    assert row["fecha"] == "2026-05-01"
    assert row["total_bruto"] == 3995.0
    assert row["total_impuestos"] == 609.40678
    assert row["total_neto"] == 3385.59322


def test_worker_process_file_logic_accepts_iso_datetime_in_date_column(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "ID_TRANSACCION,FECHA,HORA,TOTALBRUTO,TOTALIMPUESTOS,TOTALNETO,NUMSERIE",
        "704401,2026-07-25 00:00:00,0,351.5600,98.4400,450.0000,10026",
    ])
    config = {
        "nombre": "DOMINOS PIZZA",
        "id": "local-1",
        "mall_id": "mall-1",
        "codigo_interno": "26",
        "file_type": "TXT",
        "mapping_config": {
            "factura_numero": "ID_TRANSACCION",
            "fecha_venta": "FECHA",
            "hora_transaccion": "HORA",
            "total_bruto": "TOTALBRUTO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALNETO",
        },
        "constants_config": {
            "_date_format": "YYYY-MM-DD",
            "local_codigo": "26",
        },
    }

    count, errors, stats = worker.process_file_logic(
        config,
        "output_25072026.txt",
        content,
    )

    assert count == 1
    assert errors == []
    assert stats["date_min"] == "2026-07-25"
    assert stats["date_max"] == "2026-07-25"
    row = fake_db.tables["ventas"][0]
    assert row["factura_no"] == "704401"
    assert row["fecha"] == "2026-07-25"
    assert row["total_bruto"] == 351.56
    assert row["total_impuestos"] == 98.44
    assert row["total_neto"] == 450.0


def test_worker_process_file_logic_removes_configured_special_characters(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "ID_TRANSACCION,FECHA,TOTALBRUTO,TOTALIMPUESTOS,TOTALNETO",
        '"INV#1001","2026-03-06","1#18.00","1#8.00","1#00.00"',
    ])
    config = {
        "nombre": "Prestige",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "CSV",
        "mapping_config": {
            "factura_numero": "ID_TRANSACCION",
            "fecha_venta": "FECHA",
            "total_bruto": "TOTALBRUTO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALNETO",
        },
        "constants_config": {
            "_remove_special_chars": "true",
            "_special_chars_to_remove": "#",
        },
    }

    count, errors, _stats = worker.process_file_logic(config, "prestige.csv", content)

    assert count == 1
    assert errors == []
    row = fake_db.tables["ventas"][0]
    assert row["factura_no"] == "INV1001"
    assert row["fecha"] == "2026-03-06"
    assert row["total_bruto"] == 118.0
    assert row["total_impuestos"] == 18.0
    assert row["total_neto"] == 100.0


def test_worker_process_file_logic_flattens_nested_json_mapping(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = """
    {
      "sales": [
        {
          "invoiceDate": "2026-07-25",
          "invoiceNumber": "CK-1001",
          "totals": {
            "subtotal": 1000,
            "taxTotal": 180,
            "grandTotal": 1180
          },
          "fiscalData": {"ncf": "B0200000001"}
        }
      ]
    }
    """
    config = {
        "nombre": "Calvin Klein",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "JSON",
        "mapping_config": {
            "fecha_venta": "invoiceDate",
            "factura_numero": "invoiceNumber",
            "total_bruto": "totals.subtotal",
            "total_impuestos": "totals.taxTotal",
            "total_neto": "totals.grandTotal",
        },
        "constants_config": {},
    }

    count, errors, stats = worker.process_file_logic(config, "ventas_20260725.json", content)

    assert count == 1
    assert errors == []
    assert stats["processing_error_count"] == 0
    row = fake_db.tables["ventas"][0]
    assert row["factura_no"] == "CK-1001"
    assert row["fecha"] == "2026-07-25"
    assert row["total_bruto"] == 1000.0
    assert row["total_impuestos"] == 180.0
    assert row["total_neto"] == 1180.0


def test_worker_inserts_new_rows_and_documents_exact_duplicates(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    fake_db.tables["ventas"] = [
        {
            "local_id": "local-1",
            "fecha": "2026-07-25",
            "factura_no": "1168160",
            "total_bruto": 500.0,
        }
    ]
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "factura,fecha,bruto,impuestos,neto",
        "1168160,2026-07-25,500,90,410",
        "1168161,2026-07-25,750,135,615",
    ])
    config = {
        "nombre": "Pollo Victorina",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "CSV",
        "mapping_config": {
            "factura_numero": "factura",
            "fecha_venta": "fecha",
            "total_bruto": "bruto",
            "total_impuestos": "impuestos",
            "total_neto": "neto",
        },
        "constants_config": {},
    }

    count, details, stats = worker.process_file_logic(config, "DailySales.csv", content)
    estado, mensaje, confirmed = worker._resolve_worker_processing_outcome(count, details, stats)

    assert count == 1
    assert stats["duplicate_skipped"] == 1
    assert stats["processing_error_count"] == 0
    assert details == [
        {
            "linea": 2,
            "tipo": "duplicado",
            "accion": "omitido",
            "origen": "base_datos",
            "local_id": "local-1",
            "fecha": "2026-07-25",
            "factura_no": "1168160",
            "error": "Registro duplicado omitido: factura 1168160, fecha 2026-07-25.",
        }
    ]
    assert estado == "parcial"
    assert confirmed is True
    assert "1 registros nuevos" in mensaje
    assert "1 registros duplicados omitidos y documentados" in mensaje
    inserted = [row for row in fake_db.tables["ventas"] if row["factura_no"] == "1168161"]
    assert len(inserted) == 1
    assert fake_db.upsert_calls[0]["on_conflict"] == "local_id,fecha,factura_no"
    assert fake_db.upsert_calls[0]["ignore_duplicates"] is True


def test_worker_atomically_ignores_duplicate_if_prefilter_misses_it(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    fake_db.tables["ventas"] = [
        {
            "local_id": "local-1",
            "mall_id": "mall-1",
            "fecha": "2026-07-25",
            "factura_no": "1168160",
            "total_bruto": 500.0,
        }
    ]
    monkeypatch.setattr(worker, "supabase", fake_db)
    monkeypatch.setattr(
        worker,
        "_filter_existing_sale_rows",
        lambda rows, line_numbers, _local_id: (rows, line_numbers, []),
    )

    content = "\n".join([
        "factura,fecha,bruto,impuestos,neto",
        "1168160,2026-07-25,500,90,410",
        "1168161,2026-07-25,750,135,615",
    ])
    config = {
        "nombre": "Pollo Victorina",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "CSV",
        "mapping_config": {
            "factura_numero": "factura",
            "fecha_venta": "fecha",
            "total_bruto": "bruto",
            "total_impuestos": "impuestos",
            "total_neto": "neto",
        },
        "constants_config": {},
    }

    count, details, stats = worker.process_file_logic(config, "DailySales.csv", content)

    assert count == 1
    assert stats["duplicate_skipped"] == 1
    assert stats["processing_error_count"] == 0
    assert details[0]["tipo"] == "duplicado"
    assert details[0]["origen"] == "conflicto_base_datos"
    assert fake_db.upsert_calls[0]["ignore_duplicates"] is True
    assert len(fake_db.tables["ventas"]) == 2


def test_worker_accepts_zero_value_sale_when_all_totals_are_zero(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "factura,fecha,bruto,impuestos,neto",
        "VOID-100,2026-07-25,0,0,0",
    ])
    config = {
        "nombre": "Pollo Victorina",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "CSV",
        "mapping_config": {
            "factura_numero": "factura",
            "fecha_venta": "fecha",
            "total_bruto": "bruto",
            "total_impuestos": "impuestos",
            "total_neto": "neto",
        },
        "constants_config": {},
    }

    count, errors, stats = worker.process_file_logic(config, "DailySales.csv", content)

    assert count == 1
    assert errors == []
    assert stats["processing_error_count"] == 0
    assert fake_db.tables["ventas"][0]["total_bruto"] == 0.0


def test_worker_moving_window_skips_existing_documents(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_db = _FakeWorkerSupabase()
    fake_db.tables["ventas"] = [
        {
            "local_id": "local-1",
            "fecha": "2026-05-01",
            "factura_no": "632026050110",
            "total_bruto": 8170.0,
        }
    ]
    monkeypatch.setattr(worker, "supabase", fake_db)

    content = "\n".join([
        "ID_TRANSACCION,FECHA,TOTALBRUTO,TOTALIMPUESTOS,TOTALNETO",
        "632026050110,20260501,8170.0,1470.6,6699.4",
        "632026050210,20260502,19155.0,3447.9,15707.1",
    ])
    config = {
        "nombre": "ZH_PC",
        "id": "local-1",
        "mall_id": "mall-1",
        "file_type": "CSV",
        "mapping_config": {
            "factura_numero": "ID_TRANSACCION",
            "fecha_venta": "FECHA",
            "total_bruto": "TOTALBRUTO",
            "total_impuestos": "TOTALIMPUESTOS",
            "total_neto": "TOTALNETO",
        },
        "constants_config": {
            "_moving_window_mode": "true",
        },
    }

    count, errors, stats = worker.process_file_logic(config, "ZH_PC.txt", content)

    assert count == 1
    assert len(errors) == 1
    assert errors[0]["tipo"] == "duplicado"
    assert errors[0]["fecha"] == "2026-05-01"
    assert errors[0]["factura_no"] == "632026050110"
    assert stats["moving_window_mode"] is True
    assert stats["duplicate_skipped"] == 1
    assert stats["processing_error_count"] == 0
    assert stats["date_min"] == "2026-05-01"
    assert stats["date_max"] == "2026-05-02"
    inserted = [row for row in fake_db.tables["ventas"] if row["factura_no"] == "632026050210"]
    assert len(inserted) == 1
    assert inserted[0]["fecha"] == "2026-05-02"


def test_worker_moving_window_all_duplicates_is_success(monkeypatch):
    worker = _load_worker(monkeypatch)

    estado, mensaje, confirmed = worker._resolve_worker_processing_outcome(
        0,
        [],
        {
            "moving_window_mode": True,
            "duplicate_skipped": 2,
            "date_min": "2026-05-01",
            "date_max": "2026-05-02",
        },
    )

    assert estado == "exito"
    assert confirmed is True
    assert "Archivo de ventana móvil procesado" in mensaje
    assert "0 registros nuevos insertados" in mensaje
    assert "2 registros ya existentes omitidos" in mensaje


def test_worker_standard_file_all_duplicates_is_success(monkeypatch):
    worker = _load_worker(monkeypatch)
    details = [
        {
            "linea": 2,
            "tipo": "duplicado",
            "accion": "omitido",
            "fecha": "2026-07-25",
            "factura_no": "1168160",
        }
    ]

    estado, mensaje, confirmed = worker._resolve_worker_processing_outcome(
        0,
        details,
        {
            "moving_window_mode": False,
            "duplicate_skipped": 1,
            "processing_error_count": 0,
        },
    )

    assert estado == "exito"
    assert confirmed is True
    assert "sin registros nuevos" in mensaje
    assert "1 registros duplicados omitidos y documentados" in mensaje


def test_worker_marks_error_when_no_insert_is_confirmed(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({"ventas_20260301.json": b'{"rows":[]}'})
    triggered = []

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "process_file_logic", lambda config, filename, content: (0, []))
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "run_local_risk_analysis_if_possible", lambda *args, **kwargs: triggered.append(True))

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "JSON",
        "accion_post_procesado": "RENOMBRAR_BACKUP",
        "prefijo_backup": "MS02_",
    })

    assert fake_sftp.renames == [("ventas_20260301.json", "ERR_ventas_20260301.json")]
    assert triggered == []


def test_worker_marks_success_with_pr_prefix_after_confirmed_insert(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({"ventas_20260301.json": b'{"rows":[{"ok":true}]}'})
    triggered = []

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "process_file_logic", lambda config, filename, content: (12, []))
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "run_local_risk_analysis_if_possible", lambda *args, **kwargs: triggered.append(kwargs.get("trigger")))

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "JSON",
        "accion_post_procesado": "RENOMBRAR_BACKUP",
        "prefijo_backup": "MS02_",
    })

    assert fake_sftp.renames == [("ventas_20260301.json", "PR_ventas_20260301.json")]
    assert triggered == ["worker_auto_import"]


def test_worker_builds_no_new_file_message_from_last_import_log(monkeypatch):
    worker = _load_worker(monkeypatch)
    monkeypatch.setattr(worker, "supabase", _FakeLogSupabase([
        {
            "fecha_hora": "2026-05-31T13:15:00-04:00",
            "archivo": "ventas_20260531.csv",
            "estado": "exito",
            "records_processed": 259,
        }
    ]))

    message = worker._build_no_new_file_message({"id": "local-1"})

    assert message == "Archivo nuevo no encontrado, ultimo archivo importado fecha 31/05/2026"


def test_worker_logs_no_new_file_message_when_sftp_has_no_pending_files(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({})
    logs = []

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "_build_no_new_file_message", lambda config: "Archivo nuevo no encontrado, ultimo archivo importado fecha 31/05/2026")
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: logs.append((args, kwargs)))

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "CSV",
    })

    assert logs[0][0][3] == "Archivo nuevo no encontrado, ultimo archivo importado fecha 31/05/2026"
    assert logs[0][1]["metadata"]["reason"] == "no_new_file"
    assert logs[0][1]["records_processed"] == 0


def test_worker_empty_file_outcome_uses_zero_data_message(monkeypatch):
    worker = _load_worker(monkeypatch)
    fake_sftp = _FakeSFTP({"ventas_20260301.csv": b"fecha_venta,total_bruto\n"})
    logs = []

    monkeypatch.setattr(worker, "connect_with_retries", lambda connector, attempts=3, base_delay=2: connector())
    monkeypatch.setattr(worker, "get_sftp_client", lambda *args, **kwargs: (_FakeSSH(), fake_sftp))
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: logs.append((args, kwargs)))
    monkeypatch.setattr(worker, "run_local_risk_analysis_if_possible", lambda *args, **kwargs: None)

    worker.process_local_files({
        "nombre": "Cafe Santo Domingo",
        "id": "local-1",
        "mall_id": "mall-1",
        "sftp_protocol": "SFTP",
        "sftp_host": "example.com",
        "sftp_port": 22,
        "sftp_user": "demo",
        "sftp_pass": "secret",
        "sftp_path": ".",
        "file_type": "CSV",
        "mapping_config": {
            "fecha_venta": "fecha_venta",
            "total_bruto": "total_bruto",
        },
    })

    assert logs[0][0][3] == "Archivo leido con 0 Datos"
    assert logs[0][0][2] == "error"
    assert fake_sftp.renames == [("ventas_20260301.csv", "ERR_ventas_20260301.csv")]


def test_worker_strips_legacy_custom_prefix_when_building_standard_marker(monkeypatch):
    worker = _load_worker(monkeypatch)

    assert worker._build_marked_filename(
        "MS02_ventas_20260301.json",
        worker.AUTO_SUCCESS_PREFIX,
        ("MS02_",),
    ) == "PR_ventas_20260301.json"

import importlib
import asyncio
import io
import json
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


class _FakeTable:
    def __init__(self, inserted_rows):
        self.inserted_rows = inserted_rows
        self._payload = None

    def insert(self, payload):
        self._payload = payload
        return self

    def update(self, _payload):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._payload is not None:
            if isinstance(self._payload, list):
                self.inserted_rows.extend(self._payload)
            else:
                self.inserted_rows.append(self._payload)
        return SimpleNamespace(data=None)


class _FakeSupabase:
    def __init__(self, inserted_rows):
        self.inserted_rows = inserted_rows

    def table(self, _name):
        return _FakeTable(self.inserted_rows)


class _AsyncNullContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_worker_process_file_logic_generates_invoice_sequence(monkeypatch):
    worker = _load_worker(monkeypatch)
    inserted_rows = []
    monkeypatch.setattr(worker, "supabase", _FakeSupabase(inserted_rows))

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

    count, errors = worker.process_file_logic(config, "ventas.csv", content)

    assert count == 2
    assert errors == []
    assert [row["factura_no"] for row in inserted_rows] == [
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

    count, errors = worker.process_file_logic(config, "ventas.csv", content)

    assert count == 1
    assert len(errors) == 1
    assert errors[0]["linea"] == 2
    assert "periodo cerrado" in errors[0]["error"]
    assert fake_db.tables["ventas"][0]["factura_no"] == "PABT01202606010002"
    assert fake_db.tables["ventas"][0]["fecha"] == "2026-06-01"


def test_worker_process_file_logic_parses_comma_decimal_mapping(monkeypatch):
    worker = _load_worker(monkeypatch)
    inserted_rows = []
    monkeypatch.setattr(worker, "supabase", _FakeSupabase(inserted_rows))

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

    count, errors = worker.process_file_logic(config, "ventas.txt", content)

    assert count == 1
    assert errors == []
    row = inserted_rows[0]
    assert row["factura_no"] == "E320000378096"
    assert row["fecha"] == "2026-05-01"
    assert row["total_bruto"] == 3995.0
    assert row["total_impuestos"] == 609.40678
    assert row["total_neto"] == 3385.59322


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


def test_worker_strips_legacy_custom_prefix_when_building_standard_marker(monkeypatch):
    worker = _load_worker(monkeypatch)

    assert worker._build_marked_filename(
        "MS02_ventas_20260301.json",
        worker.AUTO_SUCCESS_PREFIX,
        ("MS02_",),
    ) == "PR_ventas_20260301.json"


def test_worker_processes_nested_json_using_dot_mapping(monkeypatch):
    worker = _load_worker(monkeypatch)
    inserted_rows = []
    monkeypatch.setattr(worker, "supabase", _FakeSupabase(inserted_rows))

    content = json.dumps({
        "rows": [
            {
                "invoiceNumber": "1001",
                "invoiceDate": "2026-03-06",
                "totals": {"grandTotal": 118.0, "taxTotal": 18.0, "subTotal": 100.0},
                "fiscalData": {"ncf": "B0100001"},
            },
            {
                "invoiceNumber": "1002",
                "invoiceDate": "2026-03-06",
                "totals": {"grandTotal": 59.0, "taxTotal": 9.0, "subTotal": 50.0},
                "fiscalData": {"ncf": "B0100002"},
            },
        ]
    })

    count, errors = worker.process_file_logic(
        {
            "nombre": "Cafe Santo Domingo",
            "id": "local-1",
            "mall_id": "mall-1",
            "file_type": "JSON",
            "mapping_config": {
                "factura_numero": "invoiceNumber",
                "fecha_venta": "invoiceDate",
                "total_bruto": "totals.grandTotal",
                "total_impuestos": "totals.taxTotal",
                "total_neto": "totals.subTotal",
            },
            "constants_config": {
                "local_codigo": "L003",
            },
        },
        "MS02_ventas_20260306.json",
        content,
    )

    assert count == 2
    assert errors == []
    assert [row["factura_no"] for row in inserted_rows] == ["1001", "1002"]
    assert inserted_rows[0]["fecha"] == "2026-03-06"
    assert inserted_rows[0]["total_bruto"] == 118.0
    assert inserted_rows[0]["total_impuestos"] == 18.0
    assert inserted_rows[0]["total_neto"] == 100.0


def test_worker_returns_failure_details_and_system_log_includes_them(monkeypatch):
    worker = _load_worker(monkeypatch)
    inserted_rows = []
    logs = []

    async def _noop_mark_local_status(*_args, **_kwargs):
        return None

    monkeypatch.setattr(worker, "supabase", _FakeSupabase(inserted_rows))
    monkeypatch.setattr(
        worker,
        "process_local_files",
        lambda local: {
            "ok": False,
            "message": "Lote completado: 0/1 archivos procesados. Worker: No se confirmó inserción en BD. Se encontraron 2 errores.",
            "details": [
                {"linea": 2, "error": "Datos incompletos"},
                {"linea": 3, "error": "Datos incompletos"},
            ],
        },
    )
    monkeypatch.setattr(worker, "insert_load_log", lambda *args, **kwargs: logs.append((args, kwargs)))
    monkeypatch.setattr(worker, "mark_local_status", _noop_mark_local_status)

    asyncio.run(
        worker.process_local_safe(
            {
                "nombre": "Cafe Santo Domingo",
                "id": "local-1",
                "mall_id": "mall-1",
                "consecutive_failures": 0,
                "processing_status": "IDLE",
            },
            _AsyncNullContext(),
            _AsyncNullContext(),
        )
    )

    assert logs, "Se esperaba un log de error SYSTEM"
    args, kwargs = logs[0]
    assert args[1] == "SYSTEM"
    assert "Async processing failed: Lote completado: 0/1 archivos procesados." in args[3]
    assert kwargs["detalles"] == [
        {"linea": 2, "error": "Datos incompletos"},
        {"linea": 3, "error": "Datos incompletos"},
    ]

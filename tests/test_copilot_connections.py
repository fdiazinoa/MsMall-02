import ast
import json
import logging
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from fastapi import HTTPException

from services.copilot_connections_service import (
    CONNECTION_COLUMNS,
    CONNECTION_SOURCES,
    EXPORTER_COLUMNS,
    load_copilot_connection_inventory,
)


class Query:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.after = -1

    def select(self, columns):
        assert columns == (CONNECTION_COLUMNS if self.table == "locales" else EXPORTER_COLUMNS)
        return self

    def eq(self, column, value):
        assert column == "mall_id"
        self.mall_id = value
        return self

    def order(self, column):
        assert column == "id"
        return self

    def limit(self, value):
        self.page_size = min(value, self.client.server_cap)
        return self

    def gt(self, column, value):
        assert column == "id"
        self.after = value
        return self

    def execute(self):
        self.client.calls += 1
        if self.client.fail_at == self.client.calls:
            raise RuntimeError("Query unavailable")
        source_rows = self.client.rows if self.table == "locales" else self.client.exporters
        rows = sorted((row for row in source_rows
                       if row["mall_id"] == self.mall_id and row["id"] > self.after),
                      key=lambda row: row["id"])
        return SimpleNamespace(data=rows[:self.page_size])


class Client:
    def __init__(self, rows, server_cap=500, fail_at=None, exporters=None):
        self.rows = rows
        self.exporters = exporters or []
        self.server_cap = server_cap
        self.fail_at = fail_at
        self.calls = 0

    def table(self, name):
        assert name in {"locales", "exporter_webservice_configs"}
        return Query(self, name)


def local(index, protocol="FTP", mall="mall-1"):
    return {"id": index, "mall_id": mall, "nombre": f"Local {index:04}",
            "codigo_interno": index, "sftp_protocol": protocol,
            "sftp_password": "secret-password", "sftp_host": "private-host"}


@pytest.mark.parametrize("server_cap", [500, 70])
def test_inventory_is_complete_even_with_lower_server_cap(server_cap):
    client = Client([local(i) for i in range(1101)] + [local(1200, mall="other")], server_cap)
    result = load_copilot_connection_inventory(client, "mall-1")
    assert result["total_locales"] == 1101
    assert result["por_tipo"]["FTP"]["total"] == 1101
    assert len(result["por_tipo"]["FTP"]["locales"]) == 1101
    assert result["por_tipo"]["FTP"]["locales"][-1]["codigo"] == 1100
    assert "secret-password" not in json.dumps(result)
    assert "private-host" not in json.dumps(result)


def test_protocol_normalization_unknown_and_missing_are_not_assumed_sftp():
    protocols = [" ftp ", "SFTP", "api", "web service", "WEB_SERVICE", "web-service", "LOCAL", None, "", "https://secret"]
    result = load_copilot_connection_inventory(Client([local(i, p) for i, p in enumerate(protocols)]), "mall-1")
    assert {p: group["total"] for p, group in result["por_tipo"].items()} == {
        "FTP": 1, "SFTP": 1, "API": 1, "WEBSERVICE": 3, "LOCAL": 1, "SIN_CONFIGURAR": 2, "OTRO": 1,
    }
    assert "https://secret" not in json.dumps(result)


def test_empty_inventory_is_available_with_zero_counts():
    result = load_copilot_connection_inventory(Client([]), "mall-1")
    assert result["status"] == "disponible"
    assert result["total_locales"] == 0


def test_requires_mall_scope():
    with pytest.raises(ValueError):
        load_copilot_connection_inventory(Client([]), "")


def test_second_page_failure_does_not_return_partial_totals():
    with pytest.raises(RuntimeError):
        load_copilot_connection_inventory(Client([local(i) for i in range(501)], fail_at=2), "mall-1")


def context_namespace():
    # Execute the actual context builder without starting unrelated backend services.
    tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text())
    selected = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                              and node.name in {"_build_copilot_context", "_copilot_system_prompt"}], type_ignores=[])
    scope = {
        "Any": Any, "Dict": Dict, "datetime": datetime, "HTTPException": HTTPException,
        "supabase": Client([local(i) for i in range(90)]),
        "_ensure_operator_can_access_mall": lambda *_: None,
        "_load_copilot_locales": lambda *_: [],
        "_load_copilot_missing_days": lambda rows: {"evaluados": len(rows)},
        "_load_copilot_sales_summary": lambda rows: {"evaluados": len(rows)},
        "load_copilot_connection_inventory": load_copilot_connection_inventory,
        "CONNECTION_SOURCES": CONNECTION_SOURCES,
        "_connection_monitor_service": lambda: SimpleNamespace(get_status_summary=lambda **_: {}),
        "logger": logging.getLogger(__name__), "sanitize_sensitive_ops_error": lambda _: "unavailable",
    }
    exec(compile(selected, "main.py", "exec"), scope)
    return scope


def test_context_uses_complete_inventory_without_expanding_sales_sample():
    scope = context_namespace()
    result = scope["_build_copilot_context"]("mall-1", {})
    assert result["locales"]["total"] == 90
    assert result["locales"]["locales_evaluados"] == 0
    assert result["ventas_recientes"] == {"evaluados": 0}
    assert result["locales_por_tipo_conexion"]["por_tipo"]["FTP"]["total"] == 90
    assert "locales_por_tipo_conexion" in scope["_copilot_system_prompt"]()


def test_context_query_failure_is_unavailable_not_zero():
    scope = context_namespace()
    scope["supabase"].fail_at = 1
    result = scope["_build_copilot_context"]("mall-1", {})
    assert result["locales_por_tipo_conexion"]["status"] == "no_disponible"
    assert result["locales"]["total"] is None
    assert "por_tipo" not in result["locales_por_tipo_conexion"]


def test_context_checks_access_before_loading_inventory():
    scope = context_namespace()

    def deny(*_):
        raise HTTPException(status_code=403)

    scope["_ensure_operator_can_access_mall"] = deny
    with pytest.raises(HTTPException) as error:
        scope["_build_copilot_context"]("other", {})
    assert error.value.status_code == 403
    assert scope["supabase"].calls == 0


def exporter(index, local_id, enabled=True, mall="mall-1"):
    return {"id": index, "local_id": local_id, "enabled": enabled, "mall_id": mall,
            "notes": "private-notes"}


def test_incoming_webservice_is_visible_despite_legacy_sftp_protocol():
    client = Client([local(1, "SFTP"), local(2, "API")], exporters=[exporter(1, 1)])
    result = load_copilot_connection_inventory(client, "mall-1")
    assert result["por_tipo"]["WEBSERVICE"]["total"] == 1
    assert result["por_tipo"]["API"]["total"] == 1
    assert result["por_tipo"]["SFTP"]["total"] == 1
    assert result["total_locales"] == 2
    assert result["locales_con_varios_tipos"] == 1
    assert result["por_tipo"]["WEBSERVICE"]["locales"][0]["fuentes"] == ["exporter_webservice_configs"]
    assert "private-notes" not in json.dumps(result)


def test_webservice_both_directions_counted_once_and_blank_not_unconfigured():
    result = load_copilot_connection_inventory(
        Client([local(1, "WEBSERVICE"), local(2, None)], exporters=[exporter(1, 1), exporter(2, 2)]), "mall-1")
    assert result["por_tipo"]["WEBSERVICE"]["total"] == 2
    assert result["por_tipo"]["SIN_CONFIGURAR"]["total"] == 0
    assert result["locales_con_varios_tipos"] == 0
    assert result["por_tipo"]["WEBSERVICE"]["locales"][0]["fuentes"] == CONNECTION_SOURCES


def test_disabled_foreign_and_orphan_webservices_are_not_counted():
    result = load_copilot_connection_inventory(Client(
        [local(1), local(2), local(3, mall="other")],
        exporters=[exporter(1, 1, enabled=False), exporter(2, 2, mall="other"),
                   exporter(3, 3), exporter(4, 99)]), "mall-1")
    assert result["por_tipo"]["WEBSERVICE"]["total"] == 0
    assert result["webservices_receptores_deshabilitados"] == 1


def test_incoming_webservices_are_paginated():
    result = load_copilot_connection_inventory(Client(
        [local(i) for i in range(1001)], server_cap=70,
        exporters=[exporter(i, i) for i in range(1001)]), "mall-1")
    assert result["por_tipo"]["WEBSERVICE"]["total"] == 1001
    assert result["total_locales"] == 1001


def test_exporter_query_failure_does_not_report_false_zero():
    scope = context_namespace()
    # Two calls read locales and the terminating empty page; third reads exporters.
    scope["supabase"].fail_at = 3
    result = scope["_build_copilot_context"]("mall-1", {})
    assert result["locales_por_tipo_conexion"]["status"] == "no_disponible"
    assert result["locales"]["total"] is None

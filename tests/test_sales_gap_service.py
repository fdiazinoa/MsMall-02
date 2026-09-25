from types import SimpleNamespace

from services.sales_gap_service import (
    SALES_PAGE_SIZE,
    load_actual_sales_dates_by_local,
    load_actual_sales_dates_for_local,
    load_missing_sales_dates_for_local,
)


class _SalesQuery:
    def __init__(self, rows):
        self.rows = rows
        self.local_id = None
        self.start = None
        self.end = None

    def select(self, *_args):
        return self

    def eq(self, _column, value):
        self.local_id = value
        return self

    def in_(self, _column, values):
        self.local_ids = set(values)
        return self

    def gte(self, _column, value):
        self.start = value
        return self

    def lte(self, _column, value):
        self.end = value
        return self

    def order(self, *_args):
        return self

    def gt(self, _column, value):
        self.after_id = value
        return self

    def limit(self, value):
        self.page_size = value
        return self

    def execute(self):
        local_ids = getattr(self, "local_ids", {self.local_id})
        filtered = [
            row for row in self.rows
            if row["local_id"] in local_ids and self.start <= row["fecha"] <= self.end
        ]
        after_id = getattr(self, "after_id", None)
        if after_id is not None:
            filtered = [row for row in filtered if row["id"] > after_id]
        filtered.sort(key=lambda row: row["id"])
        return SimpleNamespace(data=filtered[:self.page_size])


class _Supabase:
    def __init__(self, rows):
        self.rows = rows

    def table(self, table_name):
        assert table_name == "ventas"
        return _SalesQuery(self.rows)


def test_shared_loader_reads_beyond_supabase_default_page_limit():
    rows = [
        {"id": index, "local_id": "local-1", "fecha": "2026-08-24"}
        for index in range(SALES_PAGE_SIZE)
    ]
    rows.append({"id": SALES_PAGE_SIZE, "local_id": "local-1", "fecha": "2026-08-30"})

    actual = load_actual_sales_dates_for_local(
        _Supabase(rows),
        local_id="local-1",
        fecha_inicio="2026-08-24",
        fecha_fin="2026-08-30",
    )

    assert actual == {"2026-08-24", "2026-08-30"}


def test_shared_missing_days_are_the_same_dates_consumed_by_audit_and_email():
    rows = [
        {"id": 1, "local_id": "local-1", "fecha": "2026-08-24T12:00:00"},
        {"id": 2, "local_id": "local-1", "fecha": "2026-08-26"},
    ]

    missing = load_missing_sales_dates_for_local(
        _Supabase(rows),
        local_id="local-1",
        fecha_inicio="2026-08-24",
        fecha_fin="2026-08-26",
    )

    assert missing == ["2026-08-25"]


def test_tenant_loader_uses_one_aggregate_rpc_instead_of_sales_pages():
    calls = []

    class RpcClient:
        def rpc(self, name, params):
            calls.append((name, params))
            return SimpleNamespace(
                execute=lambda: SimpleNamespace(data=[
                    {"local_id": "local-1", "fecha": "2026-09-01"},
                    {"local_id": "local-1", "fecha": "2026-09-02"},
                    {"local_id": "local-2", "fecha": "2026-09-02"},
                ])
            )

        def table(self, _table_name):
            raise AssertionError("The optimized path must not download raw sales rows")

    actual = load_actual_sales_dates_by_local(
        RpcClient(),
        mall_id="mall-1",
        local_ids=["local-1", "local-2"],
        fecha_inicio="2026-09-01",
        fecha_fin="2026-09-02",
    )

    assert actual == {
        "local-1": {"2026-09-01", "2026-09-02"},
        "local-2": {"2026-09-02"},
    }
    assert calls == [("audit_sales_dates", {
        "p_mall_id": "mall-1",
        "p_local_ids": ["local-1", "local-2"],
        "p_start": "2026-09-01",
        "p_end": "2026-09-02",
    })]

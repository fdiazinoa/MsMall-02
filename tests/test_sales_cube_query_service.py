import re
from types import SimpleNamespace

from services.sales_cube_query_service import fetch_sales_cube_daily_aggregates


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []
        self.orders = []
        self.page_size = 1000
        self.update_payload = None

    def select(self, *_args):
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def neq(self, column, value):
        self.filters.append(("neq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def or_(self, expression):
        match = re.fullmatch(
            r"period_date\.gt\.([^,]+),and\(period_date\.eq\.([^,]+),dimension_key\.gt\.([^)]+)\)",
            expression,
        )
        assert match
        self.filters.append(("cursor", "period_dimension", (match.group(2), match.group(3))))
        return self

    def order(self, column):
        self.orders.append(column)
        return self

    def limit(self, value):
        self.page_size = value
        return self

    def update(self, payload):
        self.update_payload = payload
        return self

    def execute(self):
        rows = list(self.rows)
        for operation, column, value in self.filters:
            if operation == "eq":
                rows = [row for row in rows if row.get(column) == value]
            elif operation == "neq":
                rows = [row for row in rows if row.get(column) != value]
            elif operation == "in":
                rows = [row for row in rows if row.get(column) in value]
            elif operation == "gte":
                rows = [row for row in rows if row.get(column) >= value]
            elif operation == "lte":
                rows = [row for row in rows if row.get(column) <= value]
            elif operation == "cursor":
                rows = [
                    row
                    for row in rows
                    if (row["period_date"], row["dimension_key"]) > value
                ]
        if self.update_payload is not None:
            for row in rows:
                row.update(self.update_payload)
            return SimpleNamespace(data=[dict(row) for row in rows])
        if self.orders:
            rows.sort(key=lambda row: tuple(row.get(column) for column in self.orders))
        return SimpleNamespace(data=[dict(row) for row in rows[: self.page_size]])


class _Supabase:
    def __init__(self, tables):
        self.tables = tables
        self.rpc_calls = []

    def table(self, table_name):
        return _Query(self.tables.get(table_name, []))

    def rpc(self, function_name, params):
        self.rpc_calls.append((function_name, params))
        return SimpleNamespace(execute=lambda: SimpleNamespace(data={"status": "ok"}))


def _aggregate_row(index):
    return {
        "mall_id": "mall-1",
        "grain": "local",
        "period_date": "2026-08-15",
        "dimension_key": f"local-{index:04d}",
        "local_id": "local-1",
        "sales_net": 80,
        "sales_gross": 100,
        "taxes": 20,
        "transaction_count": 3,
        "coverage_status": "complete",
    }


def test_month_cube_uses_complete_daily_aggregates_with_keyset_pagination():
    client = _Supabase({
        "big_data_refresh_queue": [],
        "big_data_daily_aggregates": [_aggregate_row(index) for index in range(1001)],
    })

    rows = fetch_sales_cube_daily_aggregates(
        client,
        mall_id="mall-1",
        local_ids=["local-1"],
        fecha_inicio="2026-08-01",
        fecha_fin="2026-08-31",
    )

    assert rows is not None
    assert len(rows) == 1001
    assert rows[0] == {
        "local_id": "local-1",
        "fecha": "2026-08-15",
        "total_neto": 80,
        "total_bruto": 100,
        "total_impuestos": 20,
        "transacciones": 3,
    }


def test_pending_refresh_is_rebuilt_before_reading_daily_aggregates():
    client = _Supabase({
        "big_data_refresh_queue": [
            {"mall_id": "mall-1", "affected_date": "2026-08-15", "status": "pending"}
        ],
        "big_data_daily_aggregates": [_aggregate_row(1)],
    })

    rows = fetch_sales_cube_daily_aggregates(
        client,
        mall_id="mall-1",
        local_ids=["local-1"],
        fecha_inicio="2026-08-01",
        fecha_fin="2026-08-31",
    )

    assert rows is not None
    assert len(rows) == 1
    assert client.rpc_calls == [
        (
            "refresh_big_data_aggregates",
            {
                "p_mall_id": "mall-1",
                "p_start_date": "2026-08-15",
                "p_end_date": "2026-08-15",
                "p_calculation_version": "v1",
            },
        )
    ]


def test_short_range_keeps_raw_sales_path():
    client = _Supabase({})

    rows = fetch_sales_cube_daily_aggregates(
        client,
        mall_id="mall-1",
        local_ids=["local-1"],
        fecha_inicio="2026-09-01",
        fecha_fin="2026-09-02",
    )

    assert rows is None

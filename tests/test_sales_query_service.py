from types import SimpleNamespace

from services.sales_query_service import fetch_sales_rows_keyset


class _Query:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls
        self.filters = []
        self.page_size = 1000

    def select(self, fields):
        self.fields = fields
        return self

    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self

    def lte(self, column, value):
        self.filters.append(("lte", column, value))
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, set(values)))
        return self

    def gt(self, column, value):
        self.filters.append(("gt", column, value))
        return self

    def order(self, column):
        assert column == "id"
        return self

    def limit(self, value):
        self.page_size = value
        return self

    def execute(self):
        rows = list(self.rows)
        for operation, column, value in self.filters:
            if operation == "gte":
                rows = [row for row in rows if row[column] >= value]
            elif operation == "lte":
                rows = [row for row in rows if row[column] <= value]
            elif operation == "eq":
                rows = [row for row in rows if row[column] == value]
            elif operation == "in":
                rows = [row for row in rows if row[column] in value]
            elif operation == "gt":
                rows = [row for row in rows if row[column] > value]
        rows.sort(key=lambda row: row["id"])
        chunk = rows[:self.page_size]
        self.calls.append({"filters": self.filters, "size": len(chunk), "fields": self.fields})
        return SimpleNamespace(data=chunk)


class _Supabase:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def table(self, table_name):
        assert table_name == "ventas"
        return _Query(self.rows, self.calls)


def test_fetch_sales_rows_uses_id_cursor_instead_of_offset():
    rows = [
        {"id": index, "local_id": "local-1", "fecha": "2026-08-24"}
        for index in range(1, 1002)
    ]
    client = _Supabase(rows)

    result = fetch_sales_rows_keyset(
        client,
        select_fields="local_id,fecha",
        local_ids=["local-1"],
        fecha_inicio="2026-08-24",
        fecha_fin="2026-08-30",
    )

    assert len(result) == 1001
    assert len(client.calls) == 2
    assert not any(operation == "gt" for operation, *_ in client.calls[0]["filters"])
    assert ("gt", "id", 1000) in client.calls[1]["filters"]
    assert client.calls[0]["fields"] == "id,local_id,fecha"


def test_fetch_sales_rows_returns_early_for_empty_store_scope():
    client = _Supabase([])

    result = fetch_sales_rows_keyset(
        client,
        select_fields="fecha",
        local_ids=[],
        fecha_inicio="2026-08-24",
        fecha_fin="2026-08-30",
    )

    assert result == []
    assert client.calls == []

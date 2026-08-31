from types import SimpleNamespace

from services.sales_gap_service import (
    SALES_PAGE_SIZE,
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

    def gte(self, _column, value):
        self.start = value
        return self

    def lte(self, _column, value):
        self.end = value
        return self

    def order(self, *_args):
        return self

    def range(self, start, end):
        self.range_start = start
        self.range_end = end
        return self

    def execute(self):
        filtered = [
            row for row in self.rows
            if row["local_id"] == self.local_id and self.start <= row["fecha"] <= self.end
        ]
        return SimpleNamespace(data=filtered[self.range_start:self.range_end + 1])


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

from pathlib import Path


def test_operations_center_uses_compact_layout():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "components" / "OperationsCenter.tsx").read_text(encoding="utf-8")

    assert "space-y-2 lg:h-[calc(100dvh-8rem)]" in source
    assert "max-h-[200px] space-y-2 overflow-y-auto" in source
    assert "role=\"tablist\"" in source
    assert "operations-health-panel" in source
    assert "operations-cases-panel" in source
    assert "Salud de locales" in source
    assert "Casos que explican las prioridades" in source
    assert "max-h-[280px] overflow-auto" in source
    assert "max-h-[320px] space-y-2 overflow-y-auto" in source
    assert "p-10" not in source
    assert "space-y-3 lg:h-[calc(100dvh-9rem)]" not in source


def test_operations_center_defaults_to_the_current_month_to_date():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "components" / "OperationsCenter.tsx").read_text(encoding="utf-8")

    assert "const currentMonthToDate = () =>" in source
    assert "new Date(today.getFullYear(), today.getMonth(), 1)" in source
    assert "...currentMonthToDate()" in source
    assert "start_date: filters.start_date || undefined" in source
    assert "end_date: filters.end_date || undefined" in source

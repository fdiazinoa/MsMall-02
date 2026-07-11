from pathlib import Path


def test_operations_center_uses_compact_layout():
    repo = Path(__file__).resolve().parents[1]
    source = (repo / "components" / "OperationsCenter.tsx").read_text(encoding="utf-8")

    assert "space-y-2 lg:h-[calc(100dvh-8rem)]" in source
    assert "max-h-[200px] space-y-2 overflow-y-auto" in source
    assert "max-h-[240px] overflow-auto" in source
    assert "max-h-[280px] space-y-2 overflow-y-auto" in source
    assert "p-10" not in source
    assert "space-y-3 lg:h-[calc(100dvh-9rem)]" not in source

from pathlib import Path


def test_load_detail_modal_uses_compact_horizontal_layout():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")

    assert 'data-testid="load-detail-modal"' in monitor
    assert 'max-h-[90vh] w-full max-w-5xl' in monitor
    assert 'grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-5' in monitor
    assert 'label="Mall / Local"' in monitor
    assert 'label="Via / Fecha"' in monitor
    assert 'label="Archivo / Batch"' in monitor
    assert 'label="Procesados / Errores"' in monitor


def test_load_detail_validation_stays_contained():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")

    assert 'max-h-[180px]' in monitor
    assert 'overflow-y-auto pr-1 md:grid-cols-2' in monitor
    assert 'flex items-center gap-2 rounded-xl border border-green-100' in monitor
    assert 'p-8 text-center' not in monitor

from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "components" / "StoreMaintenance.tsx"


def test_store_maintenance_uses_viewport_height_and_internal_list_scroll():
    content = SOURCE.read_text()

    assert "lg:h-[calc(100dvh-8rem)] lg:overflow-hidden" in content
    assert 'data-testid="store-maintenance-list"' in content
    assert 'data-testid="store-maintenance-list-scroll"' in content
    assert "min-h-[320px] flex-1 overflow-auto overscroll-contain" in content
    assert "sticky top-0 z-20" in content


def test_secondary_store_tools_open_in_bounded_modals():
    content = SOURCE.read_text()

    assert 'data-testid="store-maintenance-form-modal"' in content
    assert 'data-testid="store-maintenance-purge-modal"' in content
    assert content.count("max-h-[92vh]") >= 2
    assert "flex-1 overflow-y-auto p-4 sm:p-5" in content
    assert '<div className="mt-8 animate-in fade-in slide-in-from-bottom-8 duration-700 delay-150">' not in content

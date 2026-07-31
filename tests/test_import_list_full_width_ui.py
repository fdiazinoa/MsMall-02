from pathlib import Path


def test_automated_import_list_uses_full_available_workspace():
    repo = Path(__file__).resolve().parents[1]
    app_source = (repo / "App.tsx").read_text(encoding="utf-8")
    import_source = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "activeTab === 'auto-import' ? 'max-w-none' : 'max-w-7xl'" in app_source

    list_start = import_source.index(") : (\n        <div className=\"min-w-0 overflow-x-auto")
    list_end = import_source.index("{/* Quick Audit Modal */}", list_start)
    list_segment = import_source[list_start:list_end]

    assert "rounded-2xl" not in list_segment
    assert "shadow-sm" not in list_segment
    assert "max-h-[calc(100dvh-18rem)]" not in list_segment
    assert "min-w-[1120px]" in list_segment
    assert "sticky top-0" in list_segment

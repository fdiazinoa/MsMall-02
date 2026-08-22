from pathlib import Path


def test_load_monitor_keeps_logs_in_their_own_scroll_area():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")

    assert 'data-testid="load-monitor-log-scroll"' in monitor
    assert 'max-h-[60vh] min-h-[320px] overflow-auto overscroll-contain' in monitor
    assert 'className="w-full min-w-[1100px] table-fixed text-left"' in monitor
    assert 'sticky top-0 z-20' in monitor


def test_load_monitor_reserves_a_visible_action_column():
    repo = Path(__file__).resolve().parents[1]
    monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")

    assert '<col className="w-[96px]" />' in monitor
    assert 'sticky right-0 z-30' in monitor
    assert 'sticky right-0 z-10 bg-white' in monitor
    assert 'whitespace-nowrap text-xs font-bold' in monitor

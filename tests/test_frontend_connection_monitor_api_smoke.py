from pathlib import Path


def _segment(text: str, anchor: str, length: int = 1600, until: str | None = None) -> str:
    idx = text.find(anchor)
    assert idx >= 0, f"anchor not found: {anchor}"
    if until:
        end = text.find(until, idx + len(anchor))
        if end > idx:
            return text[idx:end]
    return text[idx: idx + length]


def test_api_ts_exposes_connection_monitor_endpoints():
    repo = Path(__file__).resolve().parents[1]
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")

    status_seg = _segment(api_ts, "async getConnectionsStatus", until="async getConnectionFailures")
    failures_seg = _segment(api_ts, "async getConnectionFailures", until="async retryConnection")
    retry_seg = _segment(api_ts, "async retryConnection", until="async retryFailedConnections")
    retry_batch_seg = _segment(api_ts, "async retryFailedConnections")

    assert "/connections/status?mall_id=" in status_seg
    assert "fetchJsonWithBaseFallback" in status_seg

    assert "/connections/failures?mall_id=" in failures_seg
    assert "&date=" in failures_seg

    assert "/connections/${encodeURIComponent(connectionId)}/retry" in retry_seg
    assert "method: 'POST'" in retry_seg

    assert "/connections/retry-failed?mall_id=" in retry_batch_seg
    assert "method: 'POST'" in retry_batch_seg

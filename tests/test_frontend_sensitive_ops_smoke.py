from pathlib import Path


def _segment(text: str, anchor: str, length: int = 1400, until: str | None = None) -> str:
    idx = text.find(anchor)
    assert idx >= 0, f"anchor not found: {anchor}"
    if until:
        end = text.find(until, idx + len(anchor))
        if end > idx:
            return text[idx:end]
    return text[idx: idx + length]


def test_frontend_sensitive_ops_use_backend_api_paths():
    repo = Path(__file__).resolve().parents[1]
    api_ts = (repo / "api.ts").read_text(encoding="utf-8")
    import_manager = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")
    load_monitor = (repo / "components" / "LoadMonitor.tsx").read_text(encoding="utf-8")
    store_maintenance = (repo / "components" / "StoreMaintenance.tsx").read_text(encoding="utf-8")

    remote_segment = _segment(api_ts, "async getRemoteConnections")
    assert "/remote-connections" in remote_segment
    assert ".from('remote_connections')" not in remote_segment

    save_remote_segment = _segment(api_ts, "async saveRemoteConnection")
    assert "/remote-connections" in save_remote_segment
    assert ".from('remote_connections')" not in save_remote_segment

    load_logs_segment = _segment(api_ts, "async getLoadLogs", until="async reactivateStore")
    assert "/load-logs" in load_logs_segment
    assert ".from('logs_carga')" not in load_logs_segment

    clear_logs_segment = _segment(api_ts, "async clearLoadLogs")
    assert "/load-logs?mall_id=" in clear_logs_segment

    reactivate_segment = _segment(api_ts, "async reactivateStore")
    assert "/reactivate-processing" in reactivate_segment

    custom_defs_segment = _segment(api_ts, "async getLocalCustomFieldDefinitions")
    assert "/locales/custom-fields?mall_id=" in custom_defs_segment
    assert ".from('local_custom_field_definitions')" not in custom_defs_segment

    save_custom_values_segment = _segment(api_ts, "async saveStoreCustomFields")
    assert "/custom-fields" in save_custom_values_segment
    assert ".from('local_custom_field_values')" not in save_custom_values_segment

    assert "ApiService.getRemoteConnections(currentMall.id, authToken)" in import_manager
    assert "}, authToken);" in import_manager  # saveRemoteConnection call includes token
    assert "ApiService.deleteRemoteConnection(selectedConnectionId, authToken)" in import_manager
    assert "ApiService.getLoadLogs(currentMall?.id, authToken)" in import_manager
    assert "ApiService.getLoadLogs(currentMall.id, session?.access_token)" in load_monitor
    assert "ApiService.reactivateStore(store.id, session?.access_token)" in store_maintenance
    assert "ApiService.getLocalCustomFieldDefinitions(currentMall.id, authToken, true)" in store_maintenance
    assert "ApiService.saveStoreCustomFields(savedStore.id, customValuesPayload, authToken)" in store_maintenance
    assert "custom_dimension_key: selectedCustomDimension || null" in (repo / "components" / "SalesCube.tsx").read_text(encoding="utf-8")

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
    dashboard = (repo / "components" / "Dashboard.tsx").read_text(encoding="utf-8")
    header = (repo / "components" / "Header.tsx").read_text(encoding="utf-8")
    sidebar = (repo / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
    store_import_tool = (repo / "components" / "StoreImportTool.tsx").read_text(encoding="utf-8")
    missing_days_alert = (repo / "components" / "MissingDaysAlert.tsx").read_text(encoding="utf-8")
    resend_messaging_admin = (repo / "components" / "ResendMessagingAdmin.tsx").read_text(encoding="utf-8")

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
    assert "fecha_corte_importacion: null" in import_manager
    assert "Bloquea importaciones con fecha igual o anterior." in import_manager
    assert "}, authToken);" in import_manager  # saveRemoteConnection call includes token
    assert "ApiService.deleteRemoteConnection(selectedConnectionId, authToken)" in import_manager
    assert "ApiService.getLoadLogs(currentMall?.id, authToken)" in import_manager
    assert "ApiService.getLoadLogs(currentMall.id, session?.access_token)" in load_monitor
    assert "LOAD_MONITOR_PAGE_SIZE" in load_monitor
    assert "Retroceder" in load_monitor
    assert "Siguiente" in load_monitor
    assert "Mostrando ${pageStart + 1}-${pageEnd} de ${filteredLogs.length} registros" in load_monitor
    assert "ApiService.reactivateStore(store.id, session?.access_token)" in store_maintenance
    assert "case 'store-import':" in dashboard
    assert "Importador Locales" in header
    assert "Importador Locales" in sidebar
    assert "ApiService.getStores(currentMall.id)" in store_import_tool
    assert "await ApiService.createStore(payload)" in store_import_tool
    assert "await ApiService.updateStore(existing.id" in store_import_tool
    assert "ApiService.getLocalCustomFieldDefinitions(currentMall.id, authToken, true)" in store_maintenance
    assert "ApiService.saveStoreCustomFields(savedStore.id, customValuesPayload, authToken)" in store_maintenance
    assert "custom_dimension_key: selectedCustomDimension || null" in (repo / "components" / "SalesCube.tsx").read_text(encoding="utf-8")
    assert "días con venta" in missing_days_alert
    assert "% de brecha" in missing_days_alert
    assert "const reportedDays = Math.max(0, totalDays - missingDays);" in missing_days_alert

    resend_load_segment = _segment(resend_messaging_admin, "const loadConfig = async", until="const toggleWeekday")
    assert "Promise.allSettled([statusPromise, schedulePromise])" in resend_load_segment
    assert "Promise.all([" not in resend_load_segment
    assert "const resendMissingKey = status?.configured === false;" in resend_messaging_admin
    assert "{resendMissingKey && !loading && (" in resend_messaging_admin
    assert "ApiService.saveResendSenderConfig(payload, token)" in resend_messaging_admin
    assert "Guardar remitente" in resend_messaging_admin
    assert "/admin/messaging/resend/sender" in api_ts

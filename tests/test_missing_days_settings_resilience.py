from pathlib import Path


def _segment(text: str, anchor: str, until: str) -> str:
    start = text.find(anchor)
    assert start >= 0, f"anchor not found: {anchor}"
    end = text.find(until, start + len(anchor))
    assert end > start, f"end marker not found: {until}"
    return text[start:end]


def test_missing_days_settings_get_falls_back_to_defaults():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    get_segment = _segment(
        main_py,
        '@app.get("/api/v1/admin/messaging/missing-days/settings")',
        '@app.put("/api/v1/admin/messaging/missing-days/settings")',
    )

    assert "return _default_missing_days_email_settings(mall_id)" in get_segment
    assert 'detail="No se pudo cargar la programacion de envio."' not in get_segment
    assert "logger.warning(" in get_segment


def test_missing_days_settings_load_ignores_invalid_cc_values():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    sanitize_segment = _segment(
        main_py,
        "def _sanitize_missing_days_email_settings_row",
        "def _is_missing_email_settings_table_error",
    )

    assert '_normalize_email_list(row.get("cc_emails") or [], strict=False)' in sanitize_segment
    assert '"subject_template": _normalize_email_template(' in sanitize_segment
    assert '"body_template": _normalize_email_template(' in sanitize_segment


def test_missing_days_settings_persists_email_templates():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    save_segment = _segment(
        main_py,
        '@app.put("/api/v1/admin/messaging/missing-days/settings")',
        '@app.post("/api/v1/admin/messaging/missing-days/send-now")',
    )

    assert "subject_template: Optional[str] = None" in main_py
    assert "body_template: Optional[str] = None" in main_py
    assert '"subject_template": _normalize_email_template(' in save_segment
    assert '"body_template": _normalize_email_template(' in save_segment


def test_missing_days_settings_save_reloads_persisted_row():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")
    resend_admin = (repo / "components" / "ResendMessagingAdmin.tsx").read_text(encoding="utf-8")

    save_segment = _segment(
        main_py,
        '@app.put("/api/v1/admin/messaging/missing-days/settings")',
        '@app.post("/api/v1/admin/messaging/missing-days/send-now")',
    )

    assert "def _load_missing_days_email_settings_row(mall_id: str)" in main_py
    assert "return _load_missing_days_email_settings_row(mall_id)" in save_segment
    assert "normalizeSchedule(currentMall.id, saved, payload)" in resend_admin
    assert "weekdays: saved?.weekdays || fallback?.weekdays || []" in resend_admin
    assert "send_time: saved?.send_time || fallback?.send_time || '08:00'" in resend_admin


def test_missing_days_settings_save_falls_back_without_template_columns():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    save_segment = _segment(
        main_py,
        '@app.put("/api/v1/admin/messaging/missing-days/settings")',
        '@app.post("/api/v1/admin/messaging/missing-days/send-now")',
    )

    assert "def _is_missing_email_template_columns_error(exc: Exception)" in main_py
    assert "row_with_templates = {**row, **template_fields}" in save_segment
    assert '_is_missing_email_template_columns_error(exc)' in save_segment
    assert 'upsert(\n                    row,' in save_segment
    row_segment = _segment(save_segment, "row = {", "template_fields = {")
    assert '"subject_template"' not in row_segment
    assert '"body_template"' not in row_segment


def test_resend_sender_config_is_editable_and_persisted():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    assert 'class ResendSenderUpdateRequest(BaseModel):' in main_py
    assert '@app.put("/api/v1/admin/messaging/resend/sender")' in main_py
    assert '_upsert_system_health_value_sync(RESEND_SENDER_EMAIL_KEY, from_email)' in main_py
    assert '_upsert_system_health_value_sync(RESEND_SENDER_NAME_KEY, from_name)' in main_py
    assert '.order("last_update", desc=True)' in main_py
    assert '.delete().eq("key", key).execute()' in main_py
    assert '.insert({' in main_py
    assert "sender = _resolve_resend_sender_config()" in main_py
    assert '"from": f"{sender[\'from_name\']} <{sender[\'from_email\']}>"' in main_py

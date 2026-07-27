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

    assert "return _default_missing_days_email_settings(mall_id, notification_type)" in get_segment
    assert "notification_type: str = Query(MISSING_DAYS_NOTIFICATION_TYPE)" in get_segment
    assert '.eq("notification_type", notification_type)' in get_segment
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
    assert "notification_type = _normalize_missing_days_notification_type(payload.notification_type)" in save_segment
    assert '"notification_type": notification_type' in save_segment


def test_consolidated_send_requires_admin_recipient():
    repo = Path(__file__).resolve().parents[1]
    main_py = (repo / "main.py").read_text(encoding="utf-8")

    send_segment = _segment(
        main_py,
        '@app.post("/api/v1/admin/messaging/missing-days/send-now")',
        '@app.delete("/api/v1/admin/reset-sales")',
    )

    assert "MISSING_DAYS_CONSOLIDATED_NOTIFICATION_TYPE" in send_segment
    assert "Agregue al menos un correo administrativo antes de enviar el consolidado." in send_segment


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

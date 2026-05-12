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

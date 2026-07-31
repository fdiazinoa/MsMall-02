from services.date_parsing_service import normalize_sale_date


def test_normalize_spanish_excel_meridiem_with_non_breaking_space():
    assert normalize_sale_date("7/5/2026 12:00:00 a.\u00a0m.") == "2026-05-07"
    assert normalize_sale_date("7/5/2026 1:05:06 p. m.") == "2026-05-07"


def test_normalize_spanish_excel_meridiem_respects_selected_date_order():
    value = "7/5/2026 12:00:00 a. m."
    assert normalize_sale_date(value, "DD/MM/YYYY") == "2026-05-07"
    assert normalize_sale_date(value, "MM/DD/YYYY") == "2026-07-05"


def test_normalize_sale_date_preserves_existing_datetime_formats():
    assert normalize_sale_date("2026-07-25T10:15:30Z", "YYYY-MM-DD") == "2026-07-25"
    assert normalize_sale_date("20260725 10:15:30", "YYYYmmDD") == "2026-07-25"
    assert normalize_sale_date("2026-02-30 00:00:00", "YYYY-MM-DD") is None

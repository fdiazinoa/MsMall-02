from services.missing_days_email_service import build_missing_days_email_html


def test_missing_days_email_html_contains_alert_summary_and_days():
    html = build_missing_days_email_html(
        mall_name="Mall Demo",
        local_name="Local Demo",
        fecha_inicio="2026-05-01",
        fecha_fin="2026-05-10",
        missing_details=[
            {
                "fecha": "2026-05-05",
                "causa": "Procesado con Exito (Posible archivo vacio)",
                "log_id": "abc-123",
            },
            {
                "fecha": "2026-05-08",
                "causa": "Archivo no disponible en FTP",
            },
        ],
    )

    assert "Faltan ventas para 2 dias" in html
    assert "Detalle de dias faltantes y auditoria de logs" in html
    assert "2026-05-05" in html
    assert "2026-05-08" in html
    assert "Log ID: #abc-123" in html

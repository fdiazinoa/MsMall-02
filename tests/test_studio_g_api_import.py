from worker_importacion import _map_studio_g_sale, _studio_g_date_range


def test_map_studio_g_sale_to_ventas_payload():
    config = {"id": "local-1", "mall_id": "mall-1"}
    row = {
        "IDTransaccion": 123,
        "NCF": "B0100000001",
        "Fecha": "2026-05-01T13:45:10",
        "Hora": "2026-05-01T13:45:10",
        "TotalBruto": 1000,
        "TotalImpuestos": "180.00",
        "TotalNeto": "1180.00",
    }

    mapped = _map_studio_g_sale(config, row, "AFB")

    assert mapped == {
        "local_id": "local-1",
        "mall_id": "mall-1",
        "fecha": "2026-05-01",
        "factura_no": "B0100000001",
        "comprobante": "B0100000001",
        "hora_transaccion": "13:45:10",
        "total_bruto": 1000.0,
        "total_impuestos": 180.0,
        "total_neto": 1180.0,
    }


def test_studio_g_date_range_uses_constants_for_history():
    config = {
        "constants_config": {
            "fecha_inicio": "2026-05-01",
            "fecha_fin": "2026-05-20",
        }
    }

    assert _studio_g_date_range(config) == ("2026-05-01", "2026-05-20")


def test_studio_g_preview_uses_history_before_sample(monkeypatch):
    import main

    calls = []
    historical_row = {
        "fecha": "2026-05-01",
        "factura_no": "B0100000001",
        "comprobante": "B0100000001",
        "hora_transaccion": "13:45:10",
        "total_bruto": 1000,
        "total_impuestos": 180,
        "total_neto": 1180,
    }

    def fake_fetch(config):
        constants = config["constants_config"]
        calls.append((constants["_studio_g_fecha_inicio"], constants["_studio_g_fecha_fin"]))
        return ([historical_row] if len(calls) == 2 else []), "Studio G test"

    monkeypatch.setattr(main, "fetch_studio_g_sales", fake_fetch)
    monkeypatch.setattr(main, "STUDIO_G_PREVIEW_HISTORY_DAYS", 120)

    rows = main._studio_g_preview_rows(
        main.RemoteRequest(
            protocolo="API",
            host="https://studio.example.test",
            usuario="user",
            password="secret",
            ruta="AFB",
            tipo_archivo="JSON",
        )
    )

    assert rows == [historical_row]
    assert len(calls) == 2
    assert calls[0][0] == calls[0][1]
    assert calls[1][0] < calls[1][1]

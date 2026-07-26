from pathlib import Path


def test_service_account_tokens_do_not_offer_manual_regeneration():
    source = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "SecurityTokenAdmin.tsx"
    ).read_text(encoding="utf-8")

    assert "!row.service_account_id && (" in source
    assert "Los tokens de Service Account se renuevan automáticamente desde MsExportador" in source
    assert "Automático · Service Account" in source
    assert "using client_id and client_secret" not in source

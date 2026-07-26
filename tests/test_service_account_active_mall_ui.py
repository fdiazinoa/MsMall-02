from pathlib import Path


def test_service_account_creation_is_locked_to_active_mall():
    source = (
        Path(__file__).resolve().parents[1]
        / "components"
        / "SecurityTokenAdmin.tsx"
    ).read_text(encoding="utf-8")

    handler_start = source.index("const handleCreateServiceAccount")
    handler_end = source.index("const resolveTokenExpiresIn", handler_start)
    handler = source[handler_start:handler_end]

    modal_start = source.index('title="Crear Service Account (MsExportador)"')
    modal_end = source.index('open={showCreateTokenModal}', modal_start)
    modal = source[modal_start:modal_end]

    assert "const mallId = String(currentMall?.id || '').trim();" in handler
    assert "serviceAccountForm.mall_id.trim()" not in handler
    assert "Mall activo" in modal
    assert "currentMall?.nombre" in modal
    assert "Selecciona un mall" not in modal
    assert "setServiceAccountForm((prev) => ({ ...prev, mall_id: e.target.value" not in modal

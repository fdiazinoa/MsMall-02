from pathlib import Path


def test_importer_requires_existing_local_uuid():
    repo = Path(__file__).resolve().parents[1]
    api_source = (repo / "api.ts").read_text(encoding="utf-8")
    manager_source = (repo / "components" / "ImportManager.tsx").read_text(encoding="utf-8")

    assert "Selecciona un local existente antes de guardar el importador" in api_source
    assert ".update(dbPayload)" in api_source
    assert ".eq('id', config.id)" in api_source
    assert ".select('id')" in api_source
    assert "Supabase no confirmó la actualización del local seleccionado" in api_source
    assert ".upsert(payload)" not in api_source
    assert "IMP-${Math.floor" not in api_source

    assert "-- Seleccionar local registrado --" in manager_source
    assert "Nuevo Local (Crear al guardar)" not in manager_source
    assert "Selecciona el local existente al que pertenece este importador" in manager_source
    assert 'aria-readonly="true"' in manager_source
    assert "String(log.local_id || '') === localId" in manager_source
    assert "log?.local_nombre === config.nombre" not in manager_source

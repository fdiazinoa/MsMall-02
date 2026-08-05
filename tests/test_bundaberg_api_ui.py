from pathlib import Path


def test_import_config_does_not_read_or_overwrite_existing_secret():
    api_source = (Path(__file__).resolve().parents[1] / "api.ts").read_text(encoding="utf-8")

    select_line = next(line for line in api_source.splitlines() if ".select('id,nombre,mall_id,sftp_host" in line)
    assert "sftp_pass" not in select_line
    assert "resultado_ultimo" not in select_line
    assert "password: ''" in api_source
    assert "if (config.password?.trim())" in api_source
    assert "dbPayload.sftp_pass = config.password.trim()" in api_source
    assert 'throw new Error("No se pudieron cargar las conexiones de importación.")' in api_source


def test_import_manager_exposes_bundaberg_provider_fields():
    manager_source = (
        Path(__file__).resolve().parents[1] / "components" / "ImportManager.tsx"
    ).read_text(encoding="utf-8")

    assert "Bundaberg / Ágora" in manager_source
    assert '<option value="API">API REST</option>' in manager_source
    assert "https://sibs2.com/api_agora_inv/" in manager_source
    assert "Autenticación API key" in manager_source
    assert "'API key de Bundaberg'" in manager_source
    assert "Indica la API key de Bundaberg" in manager_source
    assert "configLoadError" in manager_source
    assert "No se pudieron mostrar las conexiones" in manager_source
    assert manager_source.index("Autenticación API key") < manager_source.index(">ID TPV</label>")

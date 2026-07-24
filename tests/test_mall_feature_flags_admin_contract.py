from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_feature_flag_endpoints_are_admin_protected():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert '@app.get("/api/v1/malls/{mall_id}/feature-flags")' in source
    assert '@app.put("/api/v1/malls/{mall_id}/feature-flags/{feature_key}")' in source
    assert source.count("Depends(require_admin_access)") >= 2
    assert "BIG_DATA_FEATURE_FLAGS" in source


def test_mall_manager_exposes_big_data_entitlements():
    component = (ROOT / "components" / "MallManager.tsx").read_text(encoding="utf-8")
    api = (ROOT / "api.ts").read_text(encoding="utf-8")
    assert "Módulos contratados" in component
    assert "BIG_DATA_CORE" in component
    assert "getMallFeatureFlags" in api
    assert "updateMallFeatureFlag" in api

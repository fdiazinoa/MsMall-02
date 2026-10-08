from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_role_permissions_migration_seeds_factory_roles_and_enables_rls():
    migration = (ROOT / "20260724_role_permissions_rbac.sql").read_text()

    assert "CREATE TABLE IF NOT EXISTS public.app_roles" in migration
    assert "CREATE TABLE IF NOT EXISTS public.app_role_permissions" in migration
    assert "CREATE TABLE IF NOT EXISTS public.profile_role_assignments" in migration
    assert "ALTER TABLE public.app_roles ENABLE ROW LEVEL SECURITY" in migration
    assert "('admin', 'Administrador'" in migration
    assert "('it', 'IT'" in migration
    assert "('auditor', 'Auditor'" in migration
    assert "('visualizador', 'Visualizador'" in migration


def test_api_exposes_rbac_crud_and_uses_module_permissions_for_users():
    source = (ROOT / "main.py").read_text()

    assert '"/api/v1/admin/roles"' in source
    assert 'Depends(require_module_permission("roles", "create"))' in source
    assert 'Depends(require_module_permission("roles", "update"))' in source
    assert 'Depends(require_module_permission("roles", "delete"))' in source
    assert 'Depends(require_module_permission("users", "view"))' in source
    assert 'Depends(require_module_permission("users", "create"))' in source


def test_store_routes_enforce_assigned_permissions(monkeypatch):
    import asyncio
    import pytest
    import main
    from fastapi import HTTPException

    cases = [
        ("/api/v1/locales", "POST", "create"),
        ("/api/v1/locales/{local_id}", "PATCH", "update"),
        ("/api/v1/locales/{local_id}", "DELETE", "delete"),
        ("/api/v1/locales/custom-fields", "GET", "view"),
        ("/api/v1/locales/{local_id}/custom-fields", "GET", "view"),
        ("/api/v1/locales/{local_id}/custom-fields", "PUT", "update"),
        ("/api/v1/locales/{local_id}/reactivate-processing", "POST", "update"),
    ]
    for path, method, action in cases:
        route = next(r for r in main.app.routes if r.path == path and method in r.methods)
        dependency = next(d.call for d in route.dependant.dependencies if d.name == "operator_ctx")
        context = {
            "email": "custom-role@example.test",
            "role": "custom_role",
            "permissions": {"stores": {action: True}},
        }

        async def access_context(_user_id):
            return context

        monkeypatch.setattr(main, "_get_access_context", access_context)
        assert asyncio.run(dependency(user_id="custom-user")) is context
        context["permissions"]["stores"][action] = False
        with pytest.raises(HTTPException) as denied:
            asyncio.run(dependency(user_id="custom-user"))
        assert denied.value.status_code == 403

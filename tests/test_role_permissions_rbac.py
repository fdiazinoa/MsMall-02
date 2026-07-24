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

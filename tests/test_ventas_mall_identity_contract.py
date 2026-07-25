from pathlib import Path


def test_ventas_mall_identity_guard_is_database_enforced():
    migration = Path("20260724_fix_ventas_mall_identity.sql").read_text()

    assert "create or replace function public.enforce_venta_local_mall_identity()" in migration
    assert "from public.locales l" in migration
    assert "new.mall_id is distinct from expected_mall_id" in migration
    assert "before insert or update of local_id, mall_id on public.ventas" in migration
    assert "trg_enforce_venta_local_mall_identity" in migration

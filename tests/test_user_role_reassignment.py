from pathlib import Path

import main


class _Result:
    data = []


class _ProfilesQuery:
    def __init__(self):
        self.payload = None
        self.on_conflict = None

    def upsert(self, payload, on_conflict=None):
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self):
        return _Result()


class _FakeSupabase:
    def __init__(self):
        self.profiles = _ProfilesQuery()

    def table(self, name):
        assert name == "profiles"
        return self.profiles


def test_it_role_uses_legacy_tic_profile_enum(monkeypatch):
    fake_supabase = _FakeSupabase()
    monkeypatch.setattr(main, "supabase", fake_supabase)

    main._sync_profile_role("user-1", "it")

    assert fake_supabase.profiles.payload == {"id": "user-1", "role": "tic"}
    assert fake_supabase.profiles.on_conflict == "id"


def test_profile_storage_keeps_public_roles_canonical():
    assert main._profile_storage_role("admin") == "admin"
    assert main._profile_storage_role("auditor") == "auditor"
    assert main._profile_storage_role("tic") == "tic"
    assert main._profile_storage_role("unknown") == ""


def test_reconciliation_migration_maps_it_to_tic():
    repo = Path(__file__).resolve().parents[1]
    migration = (repo / "20260716_sync_profile_roles_from_auth_metadata.sql").read_text()

    assert "when 'it' then 'tic'::public.app_role" in migration
    assert "p.role is distinct from desired_roles.role" in migration

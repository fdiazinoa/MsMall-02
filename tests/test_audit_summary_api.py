from datetime import date
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
import main


def test_summary_forwards_mall_period_and_selected_local(monkeypatch):
    calls = []
    class Client:
        def rpc(self, name, params):
            calls.append((name, params))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{'local_id': 'local'}]))
    monkeypatch.setattr(main, 'supabase', Client())
    result = main.get_audit_sales_summary(date(2026, 9, 1), date(2026, 9, 18), 'local', 'mall', {'role': 'admin'})
    assert result == [{'local_id': 'local'}]
    assert calls == [('audit_sales_summary', {'p_mall_id': 'mall', 'p_start': '2026-09-01', 'p_end': '2026-09-18', 'p_local_id': 'local'})]


def test_summary_rejects_reversed_dates():
    with pytest.raises(HTTPException) as error:
        main.get_audit_sales_summary(date(2026, 9, 18), date(2026, 9, 1), None, 'mall', {'role': 'admin'})
    assert error.value.status_code == 400


def test_summary_rejects_unassigned_mall(monkeypatch):
    monkeypatch.setattr(main, '_get_user_mall_ids', lambda user: ['other-mall'])
    with pytest.raises(HTTPException) as error:
        main.get_audit_sales_summary(date(2026, 9, 1), date(2026, 9, 18), None, 'mall', {'role': 'auditor', 'user_id': 'user'})
    assert error.value.status_code == 403

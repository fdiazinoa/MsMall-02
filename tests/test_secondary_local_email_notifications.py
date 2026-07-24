from types import SimpleNamespace

from services import missing_days_email_service as email_service


class _Query:
    def __init__(self, data):
        self.data = data
        self.single = False

    def select(self, _columns):
        return self

    def eq(self, _column, _value):
        return self

    def order(self, _column):
        return self

    def maybe_single(self):
        self.single = True
        return self

    def execute(self):
        if self.single:
            return SimpleNamespace(data=self.data[0] if self.data else None)
        return SimpleNamespace(data=self.data)


class _Supabase:
    def __init__(self):
        self.rows = {
            "malls": [{"nombre": "Mall Demo"}],
            "locales": [{
                "id": "local-1",
                "nombre": "Local Demo",
                "email": "principal@local.com",
                "email_secundario": "respaldo@local.com",
            }],
        }

    def table(self, name):
        return _Query(self.rows.get(name, []))


def test_secondary_local_email_receives_missing_days_notice_in_copy(monkeypatch):
    monkeypatch.setattr(email_service, "load_missing_days_details_for_local", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(email_service, "load_resend_sender_config", lambda *_args, **_kwargs: {
        "from_email": "notificaciones@mercasend.net",
        "from_name": "MSMALL",
    })
    sent = []

    def fake_send(to_email, _subject, _text, _html, cc_emails, **_kwargs):
        sent.append({"to": to_email, "cc": cc_emails})
        return {"id": "resend-1"}

    result = email_service.send_missing_days_emails_for_mall(
        _Supabase(),
        {
            "mall_id": "mall-1",
            "lookback_days": 7,
            "send_only_with_gaps": False,
            "cc_emails": ["respaldo@local.com", "supervision@mall.com"],
        },
        send_email=fake_send,
    )

    assert sent == [{"to": "principal@local.com", "cc": ["respaldo@local.com", "supervision@mall.com"]}]
    assert result["results"][0]["emails"] == ["principal@local.com", "respaldo@local.com"]


def test_secondary_email_can_be_the_only_notification_recipient():
    assert email_service._notification_recipient_emails({
        "email": "",
        "email_secundario": "RESPALDO@LOCAL.COM",
    }) == ["respaldo@local.com"]

import main


def test_remote_test_uses_saved_password_for_matching_connection(monkeypatch):
    monkeypatch.setattr(
        main,
        "_load_local_config_with_access",
        lambda local_id, operator_ctx: {
            "sftp_protocol": "SFTP",
            "sftp_host": "sftp.example.com",
            "sftp_pass": "stored-secret",
        },
    )
    request = main.RemoteRequest(
        local_id="local-1",
        protocolo="SFTP",
        host="sftp.example.com",
        password="",
    )

    hydrated = main._remote_request_with_saved_password(request, {"role": "admin"})

    assert hydrated.password == "stored-secret"
    assert request.password == ""


def test_remote_test_does_not_reuse_password_for_different_host(monkeypatch):
    monkeypatch.setattr(
        main,
        "_load_local_config_with_access",
        lambda local_id, operator_ctx: {
            "sftp_protocol": "SFTP",
            "sftp_host": "stored.example.com",
            "sftp_pass": "stored-secret",
        },
    )
    request = main.RemoteRequest(
        local_id="local-1",
        protocolo="SFTP",
        host="other.example.com",
        password="",
    )

    hydrated = main._remote_request_with_saved_password(request, {"role": "admin"})

    assert hydrated.password == ""


def test_remote_test_preserves_explicit_password(monkeypatch):
    def unexpected_load(*_args, **_kwargs):
        raise AssertionError("No debe consultar el secreto guardado")

    monkeypatch.setattr(main, "_load_local_config_with_access", unexpected_load)
    request = main.RemoteRequest(
        local_id="local-1",
        protocolo="SFTP",
        host="sftp.example.com",
        password="new-secret",
    )

    hydrated = main._remote_request_with_saved_password(request, {"role": "admin"})

    assert hydrated.password == "new-secret"

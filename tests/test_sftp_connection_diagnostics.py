from pathlib import Path

import paramiko

import main
from worker_importacion import _friendly_sftp_connection_error


def test_remote_test_explains_ssh_port_without_session():
    message = main._remote_connection_error_message(
        "SFTP",
        paramiko.SSHException("No existing session"),
        15.3,
    )

    assert "puerto responde" in message
    assert "negociación SSH" in message
    assert "servicio SSH/SFTP" in message


def test_worker_logs_actionable_ssh_handshake_failure():
    message = _friendly_sftp_connection_error(
        paramiko.SSHException("Error reading SSH protocol banner")
    )

    assert "puerto responde" in message
    assert "límites de sesiones" in message


def test_frontend_remote_test_prefers_direct_backend_on_vercel():
    source = (Path(__file__).resolve().parents[1] / "api.ts").read_text(encoding="utf-8")
    start = source.index("async testConnection")
    end = source.index("async exploreDirectory", start)
    segment = source[start:end]

    assert "getApiBaseUrls()" in segment
    assert "hostname.endsWith('vercel.app')" in segment
    assert "Number(left === BASE_URL) - Number(right === BASE_URL)" in segment
    assert "data.message || (data.status === 'success'" in segment

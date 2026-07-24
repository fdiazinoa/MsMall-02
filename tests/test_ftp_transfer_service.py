import socket

from services.ftp_transfer_service import retrieve_ftp_bytes


class _ControlSocket:
    def __init__(self):
        self.timeout = 10.0

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value


class _DataSocket:
    def __init__(self, data):
        self.data = data

    def recv(self, size):
        return self.data[:size]

    def close(self):
        pass


class _StalledMicrosoftFTP:
    welcome = "220 Microsoft FTP Service"
    host = "ftpagora.selfip.com"

    def __init__(self, content):
        self.content = content
        self.timeout = 10.0
        self.sock = _ControlSocket()
        self.rest_offsets = []

    def size(self, _filename):
        return len(self.content)

    def getwelcome(self):
        return self.welcome

    def retrbinary(self, _command, callback):
        callback(self.content[:1388])
        raise socket.timeout("timed out")

    def getresp(self):
        if self.sock.timeout <= 0.05:
            raise socket.timeout("no more replies")
        return "226 Transfer complete."

    def voidcmd(self, command):
        assert command == "TYPE I"
        return "200 Type set to I."

    def ntransfercmd(self, _command, rest=None):
        offset = int(rest or 0)
        self.rest_offsets.append(offset)
        return _DataSocket(self.content[offset:]), len(self.content) - offset


class _RegularFTP:
    welcome = "220 Regular FTP"

    def __init__(self, content):
        self.content = content
        self.timeout = 10.0
        self.sock = _ControlSocket()

    def size(self, _filename):
        return len(self.content)

    def retrbinary(self, _command, callback):
        callback(self.content)
        return "226 Transfer complete."

    def getwelcome(self):
        return self.welcome

    def getresp(self):
        raise socket.timeout("no pending replies")


def test_uses_rest_segments_for_stall_prone_microsoft_ftp():
    expected = (b"fecha,total\n2026-07-16,100\n" * 900)[:23270]
    ftp = _StalledMicrosoftFTP(expected)

    result = retrieve_ftp_bytes(ftp, "ZA_AG.txt")

    assert result == expected
    assert ftp.rest_offsets[0] == 0
    assert ftp.rest_offsets[-1] < len(expected)
    assert ftp.timeout == 10.0


def test_regular_transfer_still_returns_complete_payload():
    expected = b"fecha,total\n2026-07-16,100\n"

    assert retrieve_ftp_bytes(_RegularFTP(expected), "ventas.txt") == expected


def test_max_bytes_stops_after_requested_sample():
    expected = b"0123456789" * 100

    assert retrieve_ftp_bytes(_RegularFTP(expected), "ventas.txt", max_bytes=64) == expected[:64]

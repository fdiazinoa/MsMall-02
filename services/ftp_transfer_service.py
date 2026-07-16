import ftplib
import io
import logging
import socket
from typing import Optional


SEGMENTED_FTP_HOSTS = {"ftpagora.selfip.com"}


class _TransferLimitReached(Exception):
    pass


def _remote_size(ftp: ftplib.FTP, filename: str) -> Optional[int]:
    try:
        size = ftp.size(filename)
        return max(0, int(size)) if size is not None else None
    except Exception:
        return None


def _drain_transfer_replies(ftp: ftplib.FTP) -> None:
    """Consume completion/error replies left after closing a stalled data socket."""
    try:
        ftp.getresp()
    except ftplib.Error:
        # The response was consumed even when Microsoft FTP reports 550.
        pass
    except (socket.timeout, TimeoutError, OSError):
        return


def _resume_segmented_transfer(
    ftp: ftplib.FTP,
    filename: str,
    payload: io.BytesIO,
    target_bytes: int,
    chunk_size: int = 1024,
) -> None:
    """Resume a transfer in small REST ranges for FTP servers with stalled data sockets."""
    while payload.tell() < target_bytes:
        offset = payload.tell()
        ftp.voidcmd("TYPE I")
        data_socket, _ = ftp.ntransfercmd(f"RETR {filename}", rest=offset)
        try:
            chunk = data_socket.recv(min(chunk_size, target_bytes - offset))
        finally:
            data_socket.close()

        if not chunk:
            _drain_transfer_replies(ftp)
            raise ConnectionError(
                f"El servidor FTP no entrego datos al reanudar '{filename}' desde el byte {offset}."
            )

        payload.write(chunk)
        _drain_transfer_replies(ftp)


def retrieve_ftp_bytes(
    ftp: ftplib.FTP,
    filename: str,
    max_bytes: Optional[int] = None,
    logger: Optional[logging.Logger] = None,
) -> bytes:
    """Download bytes and recover servers that leave the FTP data channel open."""
    expected_size = _remote_size(ftp, filename)
    target_bytes = expected_size
    if max_bytes is not None:
        target_bytes = min(expected_size, max_bytes) if expected_size is not None else max_bytes

    payload = io.BytesIO()

    def _write(chunk: bytes) -> None:
        if target_bytes is None:
            payload.write(chunk)
            return

        remaining = target_bytes - payload.tell()
        if remaining > 0:
            payload.write(chunk[:remaining])
        if payload.tell() >= target_bytes:
            raise _TransferLimitReached

    welcome = str(getattr(ftp, "welcome", "") or "")
    if not welcome:
        try:
            welcome = str(ftp.getwelcome() or "")
        except Exception:
            welcome = ""

    # The affected Microsoft FTP server accepts RETR but stalls after one packet and
    # never closes the transfer. Starting with REST segments keeps the control session valid.
    connected_host = str(getattr(ftp, "host", "") or "").strip().lower()
    if (
        connected_host in SEGMENTED_FTP_HOSTS
        and "microsoft ftp service" in welcome.lower()
        and target_bytes is not None
    ):
        if logger:
            logger.info(
                "Usando transferencia FTP segmentada para %s (%s bytes).",
                filename,
                target_bytes,
            )
        _resume_segmented_transfer(ftp, filename, payload, target_bytes)
        return payload.getvalue()

    try:
        ftp.retrbinary(f"RETR {filename}", _write)
    except _TransferLimitReached:
        _drain_transfer_replies(ftp)
    return payload.getvalue()

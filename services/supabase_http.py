"""HTTP/1.1 avoids the terminated HTTP/2 sessions observed in the API."""
import httpx


class SupabaseReadRetryClient(httpx.Client):
    def __init__(self, **kwargs):
        super().__init__(http2=False, timeout=120, **kwargs)

    def send(self, request, **kwargs):
        try:
            return super().send(request, **kwargs)
        except httpx.TransportError:
            # Never replay writes: a lost response can follow a committed mutation.
            if request.method not in {"GET", "HEAD"}:
                raise
            return super().send(request, **kwargs)

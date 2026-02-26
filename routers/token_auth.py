import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

try:
    from supabase import create_client, Client
except Exception:  # pragma: no cover
    create_client = None
    Client = Any

logger = logging.getLogger("msmall-token-auth")
security = HTTPBearer(auto_error=False)


SCOPES_MINIMOS = {"app:read", "app:write", "export:write", "mapping:read", "tokens:manage"}
TOKEN_TYPE_APP = "app"
TOKEN_TYPE_EXPORTER = "exporter"
ACTIVE = "active"
DISABLED = "disabled"
REVOKED = "revoked"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _jwt_secret() -> str:
    secret = os.getenv("MSMALL_TOKEN_JWT_SECRET") or os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("Missing MSMALL_TOKEN_JWT_SECRET")
    return secret


def _jwt_alg() -> str:
    alg = (os.getenv("MSMALL_TOKEN_JWT_ALG") or "HS256").upper()
    if alg == "NONE":
        raise RuntimeError("JWT alg 'none' is not allowed")
    return alg


def _hash_token(secret_value: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret_value.encode("utf-8"), salt, 200_000)
    return "pbkdf2_sha256$200000$%s$%s" % (
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def _verify_hash(secret_value: str, hashed_value: str) -> bool:
    try:
        scheme, rounds, salt_b64, digest_b64 = hashed_value.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        current = hashlib.pbkdf2_hmac("sha256", secret_value.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(current, expected)
    except Exception:
        return False


def _parse_scopes(scopes: Any) -> List[str]:
    if scopes is None:
        return []
    if isinstance(scopes, str):
        raw = [s.strip() for s in scopes.replace(",", " ").split() if s.strip()]
        return sorted(set(raw))
    if isinstance(scopes, list):
        return sorted(set(str(s).strip() for s in scopes if str(s).strip()))
    return []


def _now_ts() -> int:
    return int(time.time())


def _model_dump(m: Any) -> Dict[str, Any]:
    if hasattr(m, "model_dump"):
        return m.model_dump()
    return m.dict()


class TokenConfig(BaseModel):
    app_access_minutes: int = Field(default_factory=lambda: _env_int("TOKEN_APP_ACCESS_MINUTES", 30))
    app_refresh_days: int = Field(default_factory=lambda: _env_int("TOKEN_APP_REFRESH_DAYS", 14))
    exporter_access_hours: int = Field(default_factory=lambda: _env_int("TOKEN_EXPORTER_ACCESS_HOURS", 12))
    exporter_refresh_days: int = Field(default_factory=lambda: _env_int("TOKEN_EXPORTER_REFRESH_DAYS", 90))

    def access_ttl(self, token_type: str) -> timedelta:
        return timedelta(minutes=self.app_access_minutes) if token_type == TOKEN_TYPE_APP else timedelta(hours=self.exporter_access_hours)

    def refresh_ttl(self, token_type: str) -> timedelta:
        return timedelta(days=self.app_refresh_days) if token_type == TOKEN_TYPE_APP else timedelta(days=self.exporter_refresh_days)


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._bucket: Dict[str, List[float]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.time()
        xs = [t for t in self._bucket.get(key, []) if now - t <= window_seconds]
        if len(xs) >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        xs.append(now)
        self._bucket[key] = xs


class SupabaseTokenStore:
    def __init__(self, supabase: Optional[Client]) -> None:
        self.db = supabase

    def _require_db(self):
        if not self.db:
            raise HTTPException(status_code=500, detail="Supabase no configurado para token auth")

    def create_service_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_db()
        return self.db.table("service_accounts").insert(payload).execute().data[0]

    def find_service_account_by_client_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("service_accounts").select("*").eq("client_id", client_id).maybe_single().execute()
        return res.data

    def get_service_account(self, service_account_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("service_accounts").select("*").eq("id", service_account_id).maybe_single().execute()
        return res.data

    def update_service_account(self, service_account_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._require_db()
        res = self.db.table("service_accounts").update(updates).eq("id", service_account_id).execute()
        return (res.data or [None])[0]

    def list_service_accounts(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._require_db()
        q = self.db.table("service_accounts").select("*").order("created_at", desc=True)
        for key in ["mall_id", "local_id", "token_type", "status"]:
            if filters.get(key):
                q = q.eq(key, filters[key])
        return q.execute().data or []

    def create_api_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_db()
        return self.db.table("api_tokens").insert(payload).execute().data[0]

    def update_api_token(self, token_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("api_tokens").update(updates).eq("id", token_id).execute()
        return (res.data or [None])[0]

    def get_token_by_jti(self, jti: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("api_tokens").select("*").eq("jti", jti).maybe_single().execute()
        return res.data

    def get_token_by_id(self, token_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("api_tokens").select("*").eq("id", token_id).maybe_single().execute()
        return res.data

    def list_tokens(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._require_db()
        q = self.db.table("api_tokens").select("*").order("created_at", desc=True)
        for key in ["mall_id", "local_id", "token_type", "status", "service_account_id"]:
            if filters.get(key):
                q = q.eq(key, filters[key])
        return q.execute().data or []

    def revoke_tokens_by_service_account(self, service_account_id: str, *, revoked_by: Optional[str] = None, reason: str = "service_account_bulk_revoke") -> int:
        self._require_db()
        res = (
            self.db.table("api_tokens")
            .update({
                "status": REVOKED,
                "revoked_at": utcnow().isoformat(),
                "revoked_by": revoked_by,
                "revoke_reason": reason,
                "updated_at": utcnow().isoformat(),
            })
            .eq("service_account_id", service_account_id)
            .in_("status", [ACTIVE, DISABLED])
            .execute()
        )
        return len(res.data or [])

    def revoke_tokens_by_scope(self, *, mall_id: Optional[str] = None, local_id: Optional[str] = None, revoked_by: Optional[str] = None, reason: str = "bulk revoke") -> int:
        self._require_db()
        q = self.db.table("api_tokens").update({
            "status": REVOKED,
            "revoked_at": utcnow().isoformat(),
            "revoked_by": revoked_by,
            "revoke_reason": reason,
            "updated_at": utcnow().isoformat(),
        })
        if mall_id:
            q = q.eq("mall_id", mall_id)
        if local_id:
            q = q.eq("local_id", local_id)
        q = q.in_("status", [ACTIVE, DISABLED])
        res = q.execute()
        return len(res.data or [])

    def audit(self, payload: Dict[str, Any]) -> None:
        self._require_db()
        self.db.table("token_audit_log").insert(payload).execute()

    def list_audit_logs(self, filters: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
        self._require_db()
        q = self.db.table("token_audit_log").select("*").order("created_at", desc=True).limit(limit)
        for key in ["event_type", "mall_id", "local_id", "token_id"]:
            if filters.get(key):
                q = q.eq(key, filters[key])
        return q.execute().data or []


class InMemoryTokenStore:
    def __init__(self) -> None:
        self.service_accounts: Dict[str, Dict[str, Any]] = {}
        self.api_tokens: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: List[Dict[str, Any]] = []

    def create_service_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        data.setdefault("id", str(uuid.uuid4()))
        self.service_accounts[data["id"]] = data
        return data

    def find_service_account_by_client_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        return next((x for x in self.service_accounts.values() if x.get("client_id") == client_id), None)

    def get_service_account(self, service_account_id: str) -> Optional[Dict[str, Any]]:
        return self.service_accounts.get(service_account_id)

    def update_service_account(self, service_account_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        self.service_accounts[service_account_id].update(updates)
        return self.service_accounts[service_account_id]

    def list_service_accounts(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = list(self.service_accounts.values())
        for k, v in filters.items():
            if v is not None:
                out = [x for x in out if x.get(k) == v]
        return sorted(out, key=lambda x: x.get("created_at", ""), reverse=True)

    def create_api_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload)
        data.setdefault("id", str(uuid.uuid4()))
        self.api_tokens[data["id"]] = data
        return data

    def update_api_token(self, token_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if token_id not in self.api_tokens:
            return None
        self.api_tokens[token_id].update(updates)
        return self.api_tokens[token_id]

    def get_token_by_jti(self, jti: str) -> Optional[Dict[str, Any]]:
        return next((x for x in self.api_tokens.values() if x.get("jti") == jti), None)

    def get_token_by_id(self, token_id: str) -> Optional[Dict[str, Any]]:
        return self.api_tokens.get(token_id)

    def list_tokens(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = list(self.api_tokens.values())
        for k, v in filters.items():
            if v is not None:
                out = [x for x in out if x.get(k) == v]
        return sorted(out, key=lambda x: x.get("created_at", ""), reverse=True)

    def revoke_tokens_by_scope(self, *, mall_id: Optional[str] = None, local_id: Optional[str] = None, revoked_by: Optional[str] = None, reason: str = "bulk revoke") -> int:
        n = 0
        for token in self.api_tokens.values():
            if mall_id and token.get("mall_id") != mall_id:
                continue
            if local_id and token.get("local_id") != local_id:
                continue
            if token.get("status") == REVOKED:
                continue
            token.update({"status": REVOKED, "revoked_at": utcnow().isoformat(), "revoked_by": revoked_by, "revoke_reason": reason, "updated_at": utcnow().isoformat()})
            n += 1
        return n

    def revoke_tokens_by_service_account(self, service_account_id: str, *, revoked_by: Optional[str] = None, reason: str = "service_account_bulk_revoke") -> int:
        n = 0
        for token in self.api_tokens.values():
            if token.get("service_account_id") != service_account_id:
                continue
            if token.get("status") == REVOKED:
                continue
            token.update({
                "status": REVOKED,
                "revoked_at": utcnow().isoformat(),
                "revoked_by": revoked_by,
                "revoke_reason": reason,
                "updated_at": utcnow().isoformat(),
            })
            n += 1
        return n

    def audit(self, payload: Dict[str, Any]) -> None:
        self.audit_logs.append(dict(payload))

    def list_audit_logs(self, filters: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
        out = list(self.audit_logs)
        for k, v in filters.items():
            if v is not None:
                out = [x for x in out if x.get(k) == v]
        out = sorted(out, key=lambda x: x.get("created_at", ""), reverse=True)
        return out[:limit]


@dataclass
class AuthContext:
    token_id: str
    jti: str
    mall_id: str
    local_id: Optional[str]
    token_type: str
    scopes: Set[str]
    claims: Dict[str, Any]


class TokenService:
    def __init__(self, store: Any, supabase_client: Optional[Client] = None, config: Optional[TokenConfig] = None):
        self.store = store
        self.supabase = supabase_client
        self.config = config or TokenConfig()
        self.ratelimiter = InMemoryRateLimiter()

    def _issue_jwt(self, *, token_id: str, mall_id: str, local_id: Optional[str], token_type: str, scopes: List[str], access_exp: datetime) -> str:
        now_ts = _now_ts()
        payload = {
            "sub": token_id,
            "mall_id": mall_id,
            "local_id": local_id,
            "token_type": token_type,
            "scope": scopes,
            "jti": str(uuid.uuid4()),
            "iat": now_ts,
            "exp": int(access_exp.timestamp()),
        }
        return jwt.encode(payload, _jwt_secret(), algorithm=_jwt_alg())

    def _audit(self, *, event_type: str, token: Optional[Dict[str, Any]], request: Optional[Request], metadata: Optional[Dict[str, Any]] = None):
        ip = request.client.host if request and request.client else None
        ua = request.headers.get("user-agent") if request else None
        payload = {
            "token_id": token.get("id") if token else None,
            "event_type": event_type,
            "mall_id": token.get("mall_id") if token else metadata.get("mall_id") if metadata else None,
            "local_id": token.get("local_id") if token else metadata.get("local_id") if metadata else None,
            "ip": ip,
            "ua": ua,
            "metadata": metadata or {},
            "created_at": utcnow().isoformat(),
        }
        try:
            self.store.audit(payload)
        except Exception as e:
            logger.warning("token audit failed: %s", e)

    def authenticate_app_user(self, username: str, password: str) -> Dict[str, Any]:
        if not self.supabase:
            raise HTTPException(status_code=500, detail="Supabase auth no disponible para app tokens")
        try:
            auth_res = self.supabase.auth.sign_in_with_password({"email": username, "password": password})
            user = getattr(auth_res, "user", None) or (auth_res.get("user") if isinstance(auth_res, dict) else None)
            if not user:
                raise HTTPException(status_code=401, detail="Credenciales inválidas")
            user_id = getattr(user, "id", None) or user.get("id")
            mall_rows = self.supabase.table("usuarios_malls").select("mall_id").eq("usuario_id", user_id).limit(1).execute().data or []
            if not mall_rows:
                raise HTTPException(status_code=403, detail="Usuario sin mall asignado")
            return {"user_id": user_id, "mall_id": mall_rows[0]["mall_id"]}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Auth app falló: {e}")

    def _issue_pair(
        self,
        *,
        mall_id: str,
        local_id: Optional[str],
        token_type: str,
        scopes: List[str],
        created_by: Optional[str],
        service_account_id: Optional[str],
        request: Optional[Request],
        access_ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        if token_type == TOKEN_TYPE_EXPORTER and not local_id:
            raise HTTPException(status_code=400, detail="Exporter token requiere local_id")
        now = utcnow()
        access_ttl = self.config.access_ttl(token_type)
        if access_ttl_seconds is not None and int(access_ttl_seconds) > 0:
            access_ttl = timedelta(seconds=int(access_ttl_seconds))
        access_exp = now + access_ttl
        refresh_exp = now + self.config.refresh_ttl(token_type)
        refresh_plain = secrets.token_urlsafe(48)
        token_row = self.store.create_api_token({
            "mall_id": mall_id,
            "local_id": local_id,
            "token_type": token_type,
            "scopes": scopes,
            "jti": str(uuid.uuid4()),
            "access_expires_at": access_exp.isoformat(),
            "refresh_token_hash": _hash_token(refresh_plain),
            "refresh_expires_at": refresh_exp.isoformat(),
            "status": ACTIVE,
            "created_by": created_by,
            "service_account_id": service_account_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_used_at": None,
            "last_used_ip": None,
            "last_used_ua": None,
            "revoked_at": None,
            "revoked_by": None,
            "revoke_reason": None,
        })
        access_token = self._issue_jwt(
            token_id=token_row["id"], mall_id=mall_id, local_id=local_id, token_type=token_type, scopes=scopes, access_exp=access_exp
        )
        self._audit(event_type="issued", token=token_row, request=request)
        return {
            "access_token": access_token,
            "refresh_token": refresh_plain,
            "token_type": "bearer",
            "expires_in": int(access_ttl.total_seconds()),
            "refresh_expires_in": int(self.config.refresh_ttl(token_type).total_seconds()),
            "token_id": token_row["id"],
            "jti": token_row["jti"],
            "scope": scopes,
            "mall_id": mall_id,
            "local_id": local_id,
            "token_kind": token_type,
        }

    def issue_token(self, payload: Dict[str, Any], request: Optional[Request]) -> Dict[str, Any]:
        self.ratelimiter.hit(f"token:{request.client.host if request and request.client else 'na'}", 20, 60)
        token_type = payload["token_type"]
        if token_type == TOKEN_TYPE_APP:
            auth_data = self.authenticate_app_user(payload["username"], payload["password"])
            scopes = _parse_scopes(payload.get("scopes") or ["app:read"])
            if not scopes:
                scopes = ["app:read"]
            return self._issue_pair(mall_id=auth_data["mall_id"], local_id=None, token_type=TOKEN_TYPE_APP, scopes=scopes, created_by=auth_data["user_id"], service_account_id=None, request=request)

        client_id = payload.get("client_id")
        client_secret = payload.get("client_secret")
        sa = self.store.find_service_account_by_client_id(client_id)
        if not sa or sa.get("status") != ACTIVE or not _verify_hash(client_secret or "", sa.get("client_secret_hash", "")):
            self._audit(event_type="failed", token=None, request=request, metadata={"mall_id": payload.get("mall_id"), "local_id": payload.get("local_id"), "reason": "bad exporter credentials"})
            raise HTTPException(status_code=401, detail="Credenciales exporter inválidas")
        if sa.get("token_type") != TOKEN_TYPE_EXPORTER:
            raise HTTPException(status_code=400, detail="Service account no corresponde a exporter")
        return self._issue_pair(mall_id=sa["mall_id"], local_id=sa.get("local_id"), token_type=TOKEN_TYPE_EXPORTER, scopes=_parse_scopes(sa.get("scopes")), created_by=payload.get("requested_by"), service_account_id=sa["id"], request=request)

    def refresh(self, refresh_token: str, request: Optional[Request]) -> Dict[str, Any]:
        self.ratelimiter.hit(f"refresh:{request.client.host if request and request.client else 'na'}", 30, 60)
        token_rows = self.store.list_tokens({})
        current = None
        for row in token_rows:
            if row.get("status") != ACTIVE:
                continue
            if _verify_hash(refresh_token, row.get("refresh_token_hash", "")):
                current = row
                break
        if not current:
            self._audit(event_type="failed", token=None, request=request, metadata={"reason": "refresh invalid"})
            raise HTTPException(status_code=401, detail="Refresh token inválido")
        if datetime.fromisoformat(current["refresh_expires_at"]).astimezone(timezone.utc) < utcnow():
            raise HTTPException(status_code=401, detail="Refresh token expirado")
        # rotation: revoke previous token row and issue new pair
        self.store.update_api_token(current["id"], {"status": REVOKED, "revoked_at": utcnow().isoformat(), "revoke_reason": "refresh_rotated", "updated_at": utcnow().isoformat()})
        self._audit(event_type="refreshed", token=current, request=request, metadata={"rotation": True})
        return self._issue_pair(
            mall_id=current["mall_id"],
            local_id=current.get("local_id"),
            token_type=current["token_type"],
            scopes=_parse_scopes(current.get("scopes")),
            created_by=current.get("created_by"),
            service_account_id=current.get("service_account_id"),
            request=request,
        )

    def _decode_access(self, access_token: str) -> Dict[str, Any]:
        try:
            claims = jwt.decode(access_token, _jwt_secret(), algorithms=[_jwt_alg()])
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Access token expirado")
        except Exception:
            raise HTTPException(status_code=401, detail="Access token inválido")
        if claims.get("token_type") == TOKEN_TYPE_EXPORTER and not claims.get("local_id"):
            raise HTTPException(status_code=401, detail="Exporter token sin local_id")
        return claims

    def verify_access(self, access_token: str, required_scopes: Optional[List[str]] = None, request: Optional[Request] = None) -> AuthContext:
        claims = self._decode_access(access_token)
        token_row = self.store.get_token_by_id(claims.get("sub"))
        if not token_row:
            raise HTTPException(status_code=401, detail="Token no encontrado")
        if token_row.get("status") != ACTIVE or token_row.get("revoked_at"):
            raise HTTPException(status_code=401, detail="Token revocado o inactivo")
        scopes = set(_parse_scopes(claims.get("scope")))
        missing = [s for s in (required_scopes or []) if s not in scopes]
        if missing:
            raise HTTPException(status_code=403, detail=f"Faltan scopes: {', '.join(missing)}")
        now = utcnow().isoformat()
        updates = {"last_used_at": now, "updated_at": now}
        if request and request.client:
            updates["last_used_ip"] = request.client.host
        if request:
            updates["last_used_ua"] = request.headers.get("user-agent")
        self.store.update_api_token(token_row["id"], updates)
        self._audit(event_type="used", token=token_row, request=request)
        return AuthContext(
            token_id=token_row["id"],
            jti=claims["jti"],
            mall_id=claims["mall_id"],
            local_id=claims.get("local_id"),
            token_type=claims["token_type"],
            scopes=scopes,
            claims=claims,
        )

    def revoke(self, *, token_id: Optional[str], jti: Optional[str], actor: Optional[str], reason: str, current_ctx: Optional[AuthContext], request: Optional[Request]) -> Dict[str, Any]:
        self.ratelimiter.hit(f"revoke:{request.client.host if request and request.client else 'na'}", 40, 60)
        target = None
        if token_id:
            target = self.store.get_token_by_id(token_id)
        elif jti:
            target = self.store.get_token_by_jti(jti)
        elif current_ctx:
            target = self.store.get_token_by_id(current_ctx.token_id)
        if not target:
            raise HTTPException(status_code=404, detail="Token no encontrado")
        self.store.update_api_token(target["id"], {"status": REVOKED, "revoked_at": utcnow().isoformat(), "revoked_by": actor, "revoke_reason": reason, "updated_at": utcnow().isoformat()})
        self._audit(event_type="revoked", token=target, request=request, metadata={"reason": reason})
        return {"revoked": True, "token_id": target["id"]}


class AuthTokenRequest(BaseModel):
    token_type: str = Field(..., pattern="^(app|exporter)$")
    username: Optional[str] = None
    password: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scopes: Optional[List[str]] = None


class RefreshRequest(BaseModel):
    refresh_token: str


class RevokeRequest(BaseModel):
    token_id: Optional[str] = None
    jti: Optional[str] = None
    reason: str = "manual_revoke"


class RevokeLocalRequest(BaseModel):
    mall_id: str
    local_id: str
    reason: str = "local_bulk_revoke"


class RevokeMallRequest(BaseModel):
    mall_id: str
    reason: str = "mall_bulk_revoke"


class CreateTokenRequest(BaseModel):
    mall_id: str
    local_id: Optional[str] = None
    token_type: str = Field(..., pattern="^(app|exporter)$")
    scopes: List[str]
    expires_in: Optional[int] = None
    service_account_id: Optional[str] = None


class CreateServiceAccountRequest(BaseModel):
    name: Optional[str] = None
    mall_id: str
    local_id: Optional[str] = None
    token_type: str = Field(default=TOKEN_TYPE_EXPORTER, pattern="^(exporter)$")
    scopes: List[str] = Field(default_factory=lambda: ["export:write", "mapping:read"])


class PatchTokenStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class PatchServiceAccountStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(active|disabled)$")


class RevokeServiceAccountTokensRequest(BaseModel):
    reason: str = "service_account_bulk_revoke"


def build_default_service() -> TokenService:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
    supabase_client = create_client(supabase_url, supabase_key) if (create_client and supabase_url and supabase_key) else None
    store = SupabaseTokenStore(supabase_client)
    return TokenService(store=store, supabase_client=supabase_client)


def get_token_service() -> TokenService:
    return build_default_service()


def require_token_auth(*required_scopes: str, token_types: Optional[Set[str]] = None):
    async def dep(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        svc: TokenService = Depends(get_token_service),
    ) -> AuthContext:
        if not credentials or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Bearer token requerido")
        ctx = svc.verify_access(credentials.credentials, required_scopes=list(required_scopes), request=request)
        if token_types and ctx.token_type not in token_types:
            raise HTTPException(status_code=403, detail="Tipo de token no permitido")
        return ctx
    return dep


def validate_exporter_payload_mapping(payload_mall_id: str, payload_local_id: str, ctx: AuthContext) -> None:
    if ctx.token_type != TOKEN_TYPE_EXPORTER:
        raise HTTPException(status_code=403, detail="Se requiere token exporter")
    if ctx.mall_id != payload_mall_id or ctx.local_id != payload_local_id:
        raise HTTPException(status_code=403, detail="mall_id/local_id del payload no coincide con el token")


def sanitize_token_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return row
    safe = dict(row)
    safe.pop("refresh_token_hash", None)
    return safe


def sanitize_service_account_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return row
    safe = dict(row)
    safe.pop("client_secret_hash", None)
    return safe


def create_router() -> APIRouter:
    router = APIRouter(tags=["token-auth"])

    @router.post("/auth/token")
    async def post_auth_token(payload: AuthTokenRequest, request: Request, svc: TokenService = Depends(get_token_service)):
        if payload.token_type == TOKEN_TYPE_APP and (not payload.username or not payload.password):
            raise HTTPException(status_code=400, detail="username/password requeridos para app")
        if payload.token_type == TOKEN_TYPE_EXPORTER and (not payload.client_id or not payload.client_secret):
            raise HTTPException(status_code=400, detail="client_id/client_secret requeridos para exporter")
        return svc.issue_token(_model_dump(payload), request)

    @router.post("/auth/refresh")
    async def post_auth_refresh(payload: RefreshRequest, request: Request, svc: TokenService = Depends(get_token_service)):
        return svc.refresh(payload.refresh_token, request)

    @router.post("/auth/revoke")
    async def post_auth_revoke(
        payload: RevokeRequest,
        request: Request,
        ctx: Optional[AuthContext] = Depends(require_token_auth()),
        svc: TokenService = Depends(get_token_service),
    ):
        return svc.revoke(token_id=payload.token_id, jti=payload.jti, actor=ctx.token_id if ctx else None, reason=payload.reason, current_ctx=ctx, request=request)

    @router.post("/auth/revoke/local")
    async def post_auth_revoke_local(payload: RevokeLocalRequest, request: Request, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        count = svc.store.revoke_tokens_by_scope(mall_id=payload.mall_id, local_id=payload.local_id, revoked_by=ctx.token_id, reason=payload.reason)
        return {"revoked_count": count}

    @router.post("/auth/revoke/mall")
    async def post_auth_revoke_mall(payload: RevokeMallRequest, request: Request, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        count = svc.store.revoke_tokens_by_scope(mall_id=payload.mall_id, revoked_by=ctx.token_id, reason=payload.reason)
        return {"revoked_count": count}

    @router.get("/tokens")
    async def list_tokens(
        mall_id: Optional[str] = None,
        local_id: Optional[str] = None,
        token_type: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        _: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        rows = svc.store.list_tokens({"mall_id": mall_id, "local_id": local_id, "token_type": token_type, "status": status_filter})
        return [sanitize_token_row(row) for row in rows]

    @router.get("/service-accounts")
    async def list_service_accounts(
        mall_id: Optional[str] = None,
        local_id: Optional[str] = None,
        token_type: Optional[str] = None,
        status_filter: Optional[str] = Query(None, alias="status"),
        _: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        rows = svc.store.list_service_accounts({"mall_id": mall_id, "local_id": local_id, "token_type": token_type, "status": status_filter})
        tokens = svc.store.list_tokens({"mall_id": mall_id, "local_id": local_id, "token_type": TOKEN_TYPE_EXPORTER})
        usage_by_sa: Dict[str, Dict[str, Any]] = {}
        for token in tokens:
            sa_id = token.get("service_account_id")
            if not sa_id:
                continue
            entry = usage_by_sa.setdefault(sa_id, {"last_used_at": None, "last_used_ip": None, "last_used_ua": None, "active_tokens": 0, "total_tokens": 0})
            entry["total_tokens"] += 1
            if token.get("status") == ACTIVE:
                entry["active_tokens"] += 1
            last_used_at = token.get("last_used_at")
            if last_used_at and (not entry["last_used_at"] or str(last_used_at) > str(entry["last_used_at"])):
                entry["last_used_at"] = last_used_at
                entry["last_used_ip"] = token.get("last_used_ip")
                entry["last_used_ua"] = token.get("last_used_ua")

        out: List[Dict[str, Any]] = []
        for row in rows:
            safe = sanitize_service_account_row(row)
            usage = usage_by_sa.get(safe.get("id"), {})
            safe.update({
                "last_used_at": usage.get("last_used_at"),
                "last_used_ip": usage.get("last_used_ip"),
                "last_used_ua": usage.get("last_used_ua"),
                "active_tokens": usage.get("active_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            })
            out.append(safe)
        return out

    @router.post("/tokens")
    async def create_token_manual(payload: CreateTokenRequest, request: Request, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        if payload.token_type == TOKEN_TYPE_EXPORTER and not payload.local_id:
            raise HTTPException(status_code=400, detail="local_id requerido para exporter")
        scopes = _parse_scopes(payload.scopes)
        if not scopes:
            raise HTTPException(status_code=400, detail="scopes requeridos")
        return svc._issue_pair(
            mall_id=payload.mall_id,
            local_id=payload.local_id,
            token_type=payload.token_type,
            scopes=scopes,
            created_by=ctx.token_id,
            service_account_id=payload.service_account_id,
            request=request,
            access_ttl_seconds=payload.expires_in,
        )

    @router.post("/service-accounts")
    async def create_service_account(payload: CreateServiceAccountRequest, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        if payload.token_type == TOKEN_TYPE_EXPORTER and not payload.local_id:
            raise HTTPException(status_code=400, detail="local_id requerido para exporter")
        client_id = f"msa_{secrets.token_hex(8)}"
        client_secret = secrets.token_urlsafe(32)
        row = svc.store.create_service_account({
            "name": payload.name.strip() if payload.name else None,
            "mall_id": payload.mall_id,
            "local_id": payload.local_id,
            "token_type": payload.token_type,
            "client_id": client_id,
            "client_secret_hash": _hash_token(client_secret),
            "scopes": _parse_scopes(payload.scopes),
            "status": ACTIVE,
            "created_by": ctx.token_id,
            "created_at": utcnow().isoformat(),
            "updated_at": utcnow().isoformat(),
        })
        safe_row = sanitize_service_account_row(row) or {}
        safe_row["client_secret"] = client_secret  # one-time reveal
        return safe_row

    @router.patch("/service-accounts/{service_account_id}/status")
    async def patch_service_account_status(service_account_id: str, payload: PatchServiceAccountStatusRequest, _: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        row = svc.store.update_service_account(service_account_id, {"status": payload.status, "updated_at": utcnow().isoformat()})
        if not row:
            raise HTTPException(status_code=404, detail="Service account no encontrado")
        return sanitize_service_account_row(row)

    @router.post("/service-accounts/{service_account_id}/regenerate")
    async def regenerate_service_account_secret(service_account_id: str, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        base = svc.store.get_service_account(service_account_id)
        if not base:
            raise HTTPException(status_code=404, detail="Service account no encontrado")
        client_secret = secrets.token_urlsafe(32)
        row = svc.store.update_service_account(service_account_id, {
            "client_secret_hash": _hash_token(client_secret),
            "updated_at": utcnow().isoformat(),
            "status": ACTIVE,
        })
        safe_row = sanitize_service_account_row(row) or {}
        safe_row["client_secret"] = client_secret
        safe_row["warning"] = "Este secreto no volverá a mostrarse completo."
        svc.store.revoke_tokens_by_service_account(service_account_id, revoked_by=ctx.token_id, reason="service_account_secret_regenerated")
        return safe_row

    @router.post("/service-accounts/{service_account_id}/revoke-tokens")
    async def revoke_service_account_tokens(service_account_id: str, payload: RevokeServiceAccountTokensRequest, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        base = svc.store.get_service_account(service_account_id)
        if not base:
            raise HTTPException(status_code=404, detail="Service account no encontrado")
        count = svc.store.revoke_tokens_by_service_account(service_account_id, revoked_by=ctx.token_id, reason=payload.reason)
        return {"revoked_count": count, "service_account_id": service_account_id}

    @router.patch("/tokens/{token_id}/status")
    async def patch_token_status(token_id: str, payload: PatchTokenStatusRequest, _: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        row = svc.store.update_api_token(token_id, {"status": payload.status, "updated_at": utcnow().isoformat()})
        if not row:
            raise HTTPException(status_code=404, detail="Token no encontrado")
        return sanitize_token_row(row)

    @router.post("/tokens/{token_id}/regenerate")
    async def regenerate_token(token_id: str, request: Request, ctx: AuthContext = Depends(require_token_auth("tokens:manage")), svc: TokenService = Depends(get_token_service)):
        base = svc.store.get_token_by_id(token_id)
        if not base:
            raise HTTPException(status_code=404, detail="Token no encontrado")
        svc.store.update_api_token(token_id, {"status": REVOKED, "revoked_at": utcnow().isoformat(), "revoked_by": ctx.token_id, "revoke_reason": "regenerated", "updated_at": utcnow().isoformat()})
        return svc._issue_pair(
            mall_id=base["mall_id"],
            local_id=base.get("local_id"),
            token_type=base["token_type"],
            scopes=_parse_scopes(base.get("scopes")),
            created_by=ctx.token_id,
            service_account_id=base.get("service_account_id"),
            request=request,
        )

    @router.get("/token-audit")
    async def list_token_audit(
        mall_id: Optional[str] = None,
        local_id: Optional[str] = None,
        event_type: Optional[str] = None,
        token_id: Optional[str] = None,
        limit: int = Query(200, ge=1, le=1000),
        _: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        return svc.store.list_audit_logs({"mall_id": mall_id, "local_id": local_id, "event_type": event_type, "token_id": token_id}, limit=limit)

    @router.post("/api/v1/exporter/sync/ingest")
    async def exporter_sync_ingest(payload: Dict[str, Any], ctx: AuthContext = Depends(require_token_auth("export:write", token_types={TOKEN_TYPE_EXPORTER}))):
        payload_mall_id = str(payload.get("mall_id") or "")
        payload_local_id = str(payload.get("local_id") or "")
        if not payload_mall_id or not payload_local_id:
            raise HTTPException(status_code=400, detail="mall_id y local_id son requeridos")
        validate_exporter_payload_mapping(payload_mall_id, payload_local_id, ctx)
        return {"accepted": True, "mall_id": payload_mall_id, "local_id": payload_local_id}

    return router

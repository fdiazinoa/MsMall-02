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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from services.exporter_sales_promotion_service import (
    build_sales_dedup_key,
    prepare_exporter_sales_rows,
    promote_exporter_rows_to_sales,
)
from services.load_log_service import build_load_log_payload, insert_load_log_row

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


def request_explicit_never_expires(payload: BaseModel) -> bool:
    fields_set = getattr(payload, "model_fields_set", None)
    if fields_set is None:
        fields_set = getattr(payload, "__fields_set__", set())
    return "expires_in" in fields_set and getattr(payload, "expires_in", None) is None


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

    def _extract_data(self, response: Any, *, operation: str):
        # Defensive guard: in some failure modes SDK can return None instead of a response object.
        if response is None:
            raise HTTPException(status_code=502, detail=f"Respuesta vacia de Supabase en {operation}")
        return getattr(response, "data", None)

    def create_service_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_db()
        return self.db.table("service_accounts").insert(payload).execute().data[0]

    def find_service_account_by_client_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = self.db.table("service_accounts").select("*").eq("client_id", client_id).maybe_single().execute()
        if res is None:
            return None
        return getattr(res, "data", None)

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

    def get_local_exporter_code(self, mall_id: str, local_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = (
            self.db.table("locales")
            .select("id, mall_id, codigo_interno, nombre")
            .eq("mall_id", mall_id)
            .eq("id", local_id)
            .maybe_single()
            .execute()
        )
        row = res.data or None
        if not row:
            return None
        return {
            "mall_id": row.get("mall_id"),
            "local_id": row.get("id"),
            "codigo_cliente": row.get("codigo_interno"),
            "local_nombre": row.get("nombre"),
        }

    def upsert_exporter_ingest_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        self._require_db()
        if not rows:
            return {"inserted": 0, "updated": 0}
        dedup_keys = [str(r.get("dedup_key")) for r in rows if r.get("dedup_key")]
        existing: Set[str] = set()
        if dedup_keys:
            existing_res = (
                self.db.table("exporter_sales_ingest")
                .select("dedup_key")
                .in_("dedup_key", dedup_keys)
                .execute()
            )
            existing = {str(x.get("dedup_key")) for x in (existing_res.data or []) if x.get("dedup_key")}
        stamped_rows = [{**row, "updated_at": utcnow().isoformat()} for row in rows]
        self.db.table("exporter_sales_ingest").upsert(stamped_rows, on_conflict="dedup_key").execute()
        inserted = sum(1 for key in dedup_keys if key not in existing)
        return {"inserted": inserted, "updated": len(dedup_keys) - inserted}

    def promote_exporter_ingest_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        self._require_db()
        return promote_exporter_rows_to_sales(self.db, rows, logger=logger)

    def get_exporter_webservice_config(self, mall_id: str, local_id: str) -> Optional[Dict[str, Any]]:
        self._require_db()
        res = (
            self.db.table("exporter_webservice_configs")
            .select("*")
            .eq("mall_id", mall_id)
            .eq("local_id", local_id)
            .maybe_single()
            .execute()
        )
        return self._extract_data(res, operation="get_exporter_webservice_config") or None

    def list_exporter_webservice_configs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        self._require_db()
        q = self.db.table("exporter_webservice_configs").select("*").order("updated_at", desc=True)
        if filters.get("mall_id"):
            q = q.eq("mall_id", filters["mall_id"])
        if filters.get("local_id"):
            q = q.eq("local_id", filters["local_id"])
        if filters.get("enabled") is not None:
            q = q.eq("enabled", bool(filters["enabled"]))
        res = q.execute()
        return self._extract_data(res, operation="list_exporter_webservice_configs") or []

    def upsert_exporter_webservice_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._require_db()
        now_iso = utcnow().isoformat()
        mall_id = str(payload.get("mall_id") or "")
        local_id = str(payload.get("local_id") or "")
        current = None
        if mall_id and local_id:
            try:
                current = self.get_exporter_webservice_config(mall_id, local_id)
            except HTTPException as e:
                # Continue with blind upsert if Supabase answered without payload for the pre-read.
                if e.status_code in {404, 502}:
                    logger.warning(
                        "exporter_webservice_config pre-read skipped mall=%s local=%s detail=%s",
                        mall_id,
                        local_id,
                        str(e.detail),
                    )
                else:
                    raise
        data = {**payload, "updated_at": now_iso}
        if current and current.get("id"):
            data["id"] = current.get("id")
        # Keep original created_at when available; otherwise let DB default/current row value apply.
        if current and current.get("created_at"):
            data["created_at"] = current.get("created_at")
        res = self.db.table("exporter_webservice_configs").upsert(data, on_conflict="local_id").execute()
        rows = self._extract_data(res, operation="upsert_exporter_webservice_config") or []
        if rows:
            return rows[0]
        if mall_id and local_id:
            try:
                refreshed = self.get_exporter_webservice_config(mall_id, local_id)
                if refreshed:
                    return refreshed
            except HTTPException as e:
                if e.status_code not in {404, 502}:
                    raise
        return {}


class InMemoryTokenStore:
    def __init__(self) -> None:
        self.service_accounts: Dict[str, Dict[str, Any]] = {}
        self.api_tokens: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: List[Dict[str, Any]] = []
        self.local_codes: Dict[Tuple[str, str], str] = {}
        self.local_names: Dict[Tuple[str, str], str] = {}
        self.exporter_ingest_rows: Dict[str, Dict[str, Any]] = {}
        self.sales_rows: Dict[str, Dict[str, Any]] = {}
        self.exporter_webservice_configs: Dict[Tuple[str, str], Dict[str, Any]] = {}

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

    def get_local_exporter_code(self, mall_id: str, local_id: str) -> Optional[Dict[str, Any]]:
        code = self.local_codes.get((mall_id, local_id))
        if not code:
            return None
        return {
            "mall_id": mall_id,
            "local_id": local_id,
            "codigo_cliente": code,
            "local_nombre": self.local_names.get((mall_id, local_id)),
        }

    def upsert_exporter_ingest_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        inserted = 0
        updated = 0
        for row in rows:
            key = str(row.get("dedup_key") or "")
            if not key:
                continue
            now_iso = utcnow().isoformat()
            if key in self.exporter_ingest_rows:
                self.exporter_ingest_rows[key].update({**row, "updated_at": now_iso})
                updated += 1
            else:
                self.exporter_ingest_rows[key] = {**row, "id": str(uuid.uuid4()), "created_at": now_iso, "updated_at": now_iso}
                inserted += 1
        return {"inserted": inserted, "updated": updated}

    def list_exporter_ingest_rows(self) -> List[Dict[str, Any]]:
        return list(self.exporter_ingest_rows.values())

    def promote_exporter_ingest_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, int]:
        prepared_rows = prepare_exporter_sales_rows(rows)
        inserted = 0
        updated = 0
        for row in prepared_rows:
            dedup_key = build_sales_dedup_key(row) or str(uuid.uuid4())
            now_iso = utcnow().isoformat()
            current = self.sales_rows.get(dedup_key)
            if current:
                self.sales_rows[dedup_key] = {
                    **current,
                    **row,
                    "id": current.get("id") or str(uuid.uuid4()),
                    "created_at": current.get("created_at") or now_iso,
                    "updated_at": now_iso,
                }
                updated += 1
            else:
                self.sales_rows[dedup_key] = {
                    **row,
                    "id": str(uuid.uuid4()),
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }
                inserted += 1
        return {"processed": len(prepared_rows), "inserted": inserted, "updated": updated}

    def list_sales_rows(self) -> List[Dict[str, Any]]:
        return list(self.sales_rows.values())

    def get_exporter_webservice_config(self, mall_id: str, local_id: str) -> Optional[Dict[str, Any]]:
        row = self.exporter_webservice_configs.get((mall_id, local_id))
        return dict(row) if row else None

    def list_exporter_webservice_configs(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = [dict(x) for x in self.exporter_webservice_configs.values()]
        for key, value in filters.items():
            if value is None:
                continue
            out = [x for x in out if x.get(key) == value]
        return sorted(out, key=lambda x: x.get("updated_at", ""), reverse=True)

    def upsert_exporter_webservice_config(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        mall_id = str(payload.get("mall_id") or "")
        local_id = str(payload.get("local_id") or "")
        key = (mall_id, local_id)
        now_iso = utcnow().isoformat()
        base = self.exporter_webservice_configs.get(key, {})
        row = {
            "id": base.get("id") or str(uuid.uuid4()),
            "mall_id": mall_id,
            "local_id": local_id,
            "enabled": bool(payload.get("enabled", True)),
            "contract_type": payload.get("contract_type") or "msmall_sales_v1",
            "default_granularity": payload.get("default_granularity") or "transaction",
            "allow_transaction": bool(payload.get("allow_transaction", True)),
            "allow_daily": bool(payload.get("allow_daily", True)),
            "strict_validation": bool(payload.get("strict_validation", True)),
            "notes": payload.get("notes"),
            "created_at": base.get("created_at") or now_iso,
            "updated_at": now_iso,
            "last_ingest_at": base.get("last_ingest_at"),
            "last_ingest_status": base.get("last_ingest_status"),
            "last_ingest_message": base.get("last_ingest_message"),
            "last_ingest_granularity": base.get("last_ingest_granularity"),
        }
        self.exporter_webservice_configs[key] = row
        return dict(row)


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

    def write_load_log(
        self,
        *,
        mall_id: Optional[str],
        local_id: Optional[str],
        local_nombre: Optional[str],
        archivo: str,
        estado: str,
        mensaje: str,
        batch_id: Optional[str] = None,
        detalles: Optional[List[Dict[str, Any]]] = None,
        records_processed: Optional[int] = None,
        error_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.supabase:
            return
        payload = build_load_log_payload(
            local_nombre=local_nombre or local_id or "Local desconocido",
            archivo=archivo,
            estado=estado,
            mensaje=mensaje,
            batch_id=batch_id,
            detalles=detalles,
            mall_id=mall_id,
            local_id=local_id,
            canal="WebService",
            records_processed=records_processed,
            error_count=error_count,
            metadata=metadata,
        )
        try:
            insert_load_log_row(self.supabase, payload, logger=logger)
        except Exception as exc:
            logger.warning("webservice load log failed: %s", exc)

    def _issue_jwt(self, *, token_id: str, mall_id: str, local_id: Optional[str], token_type: str, scopes: List[str], access_exp: Optional[datetime]) -> str:
        now_ts = _now_ts()
        payload = {
            "sub": token_id,
            "mall_id": mall_id,
            "local_id": local_id,
            "token_type": token_type,
            "scope": scopes,
            "jti": str(uuid.uuid4()),
            "iat": now_ts,
        }
        if access_exp is not None:
            payload["exp"] = int(access_exp.timestamp())
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
        access_never_expires: bool = False,
    ) -> Dict[str, Any]:
        if token_type == TOKEN_TYPE_EXPORTER and not local_id:
            raise HTTPException(status_code=400, detail="Exporter token requiere local_id")
        # Validate JWT configuration before writing token rows to avoid partial issuance.
        _jwt_secret()
        _jwt_alg()
        now = utcnow()
        access_ttl = self.config.access_ttl(token_type)
        if access_ttl_seconds is not None and int(access_ttl_seconds) > 0:
            access_ttl = timedelta(seconds=int(access_ttl_seconds))
        access_exp = None if access_never_expires else now + access_ttl
        refresh_exp = now + self.config.refresh_ttl(token_type)
        refresh_plain = secrets.token_urlsafe(48)
        token_row = self.store.create_api_token({
            "mall_id": mall_id,
            "local_id": local_id,
            "token_type": token_type,
            "scopes": scopes,
            "jti": str(uuid.uuid4()),
            "access_expires_at": access_exp.isoformat() if access_exp else None,
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
            "expires_in": None if access_never_expires else int(access_ttl.total_seconds()),
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
        try:
            sa = self.store.find_service_account_by_client_id(client_id)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Exporter auth lookup failed for client_id=%s: %s", client_id, e)
            raise HTTPException(status_code=503, detail="Autenticacion exporter temporalmente no disponible")

        if not isinstance(sa, dict) or sa.get("status") != ACTIVE or not _verify_hash(client_secret or "", str(sa.get("client_secret_hash") or "")):
            self._audit(event_type="failed", token=None, request=request, metadata={"mall_id": payload.get("mall_id"), "local_id": payload.get("local_id"), "reason": "bad exporter credentials"})
            raise HTTPException(status_code=401, detail="Credenciales exporter inválidas")
        if sa.get("token_type") != TOKEN_TYPE_EXPORTER:
            raise HTTPException(status_code=400, detail="Service account no corresponde a exporter")

        service_account_id = str(sa.get("id") or "").strip()
        mall_id = str(sa.get("mall_id") or "").strip()
        local_id = str(sa.get("local_id") or "").strip()
        if not service_account_id or not mall_id or not local_id:
            self._audit(
                event_type="failed",
                token=None,
                request=request,
                metadata={
                    "mall_id": mall_id or payload.get("mall_id"),
                    "local_id": local_id or payload.get("local_id"),
                    "reason": "misconfigured exporter service account",
                },
            )
            raise HTTPException(status_code=400, detail="Service account exporter incompleta (id/mall_id/local_id)")

        try:
            return self._issue_pair(
                mall_id=mall_id,
                local_id=local_id,
                token_type=TOKEN_TYPE_EXPORTER,
                scopes=_parse_scopes(sa.get("scopes")),
                created_by=payload.get("requested_by"),
                service_account_id=service_account_id,
                request=request,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(
                "Exporter token issue failed for client_id=%s service_account_id=%s: %s",
                client_id,
                service_account_id,
                e,
            )
            raise HTTPException(status_code=503, detail="Emision de token exporter temporalmente no disponible")

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


class UpsertExporterWebserviceConfigRequest(BaseModel):
    mall_id: str
    enabled: bool = True
    contract_type: str = Field(default="msmall_sales_v1", pattern="^(msmall_sales_v1)$")
    default_granularity: str = Field(default="transaction", pattern="^(transaction|daily|daily_summary)$")
    allow_transaction: bool = True
    allow_daily: bool = True
    strict_validation: bool = True
    notes: Optional[str] = None


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


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _as_str_or_none(value: Any) -> Optional[str]:
    if not _has_value(value):
        return None
    return str(value).strip()


def _pick_first_value(row: Dict[str, Any], *field_names: str) -> Tuple[Any, Optional[str]]:
    for field_name in field_names:
        if field_name not in row:
            continue
        value = row.get(field_name)
        if not _has_value(value):
            continue
        return value, field_name
    return None, None


def _normalize_granularity(value: Any) -> str:
    granularity = str(value or "transaction").strip().lower()
    if granularity in {"daily", "daily_summary"}:
        return "daily"
    return "transaction"


def _exporter_log_filename(meta: Dict[str, Any]) -> str:
    for field_name in ("filename", "file_name", "source_filename", "archivo", "batch_label"):
        value = _as_str_or_none(meta.get(field_name))
        if value:
            return value
    batch_id = _as_str_or_none(meta.get("batch_id"))
    if batch_id:
        return f"WebService batch {batch_id}"
    return "WebService payload"


def _exporter_validation_details(errors: List[str]) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for idx, error in enumerate(errors[:20], start=1):
        details.append({"linea": idx, "error": error})
    return details


def _coerce_numeric(value: Any, *, row_idx: int, field_name: str, errors: List[str]) -> Optional[float]:
    if not _has_value(value):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raw = str(value).strip()
    normalized = raw.replace(",", ".") if ("," in raw and "." not in raw) else raw
    try:
        return float(normalized)
    except Exception:
        errors.append(f"row {row_idx}: '{field_name}' debe ser numerico (valor='{raw}')")
        return None


def _coerce_int(value: Any, *, row_idx: int, field_name: str, errors: List[str]) -> Optional[int]:
    if not _has_value(value):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        errors.append(f"row {row_idx}: '{field_name}' debe ser entero")
        return None


def _normalize_date_text(value: Any) -> Optional[str]:
    if not _has_value(value):
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return text


def _normalize_time_text(value: Any) -> Optional[str]:
    if not _has_value(value):
        return None
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[1]
    if " " in text:
        text = text.split()[-1]
    return text[:8] if len(text) >= 8 else text


def _canonicalize_exporter_row(row: Dict[str, Any], *, row_idx: int, granularity: str, errors: List[str]) -> Dict[str, Any]:
    documento_numero_val, documento_numero_field = _pick_first_value(
        row, "documento_numero", "factura_numero", "ticket_numero", "InvoiceNo", "TicketNo"
    )
    documento_tipo_val, _ = _pick_first_value(row, "documento_tipo", "tipo_documento", "DocumentType")
    fecha_venta_val, _ = _pick_first_value(row, "fecha_venta", "SaleDate", "sale_date", "fecha")
    hora_venta_val, _ = _pick_first_value(row, "hora_venta", "SaleTime", "sale_time", "hora")
    total_bruto_val, _ = _pick_first_value(row, "total_bruto", "totalBruto", "GrossTotal", "gross_total")
    total_impuesto_val, _ = _pick_first_value(row, "total_impuesto", "total_impuestos", "TaxTotal", "tax_total")
    total_neto_val, _ = _pick_first_value(row, "total_neto", "NetTotal", "net_total")
    resumen_id_val, _ = _pick_first_value(row, "resumen_id", "summary_id")
    cantidad_docs_val, _ = _pick_first_value(row, "cantidad_documentos", "document_count")

    documento_numero = _as_str_or_none(documento_numero_val)
    documento_tipo = _as_str_or_none(documento_tipo_val)
    if not documento_tipo and documento_numero_field:
        f = documento_numero_field.lower()
        if "factura" in f or "invoice" in f:
            documento_tipo = "factura"
        elif "ticket" in f:
            documento_tipo = "ticket"

    normalized = {
        "documento_numero": documento_numero,
        "documento_tipo": documento_tipo,
        "fecha_venta": _normalize_date_text(fecha_venta_val),
        "hora_venta": _normalize_time_text(hora_venta_val) if granularity == "transaction" else (_normalize_time_text(hora_venta_val) if _has_value(hora_venta_val) else None),
        "total_bruto": _coerce_numeric(total_bruto_val, row_idx=row_idx, field_name="total_bruto", errors=errors),
        "total_impuesto": _coerce_numeric(total_impuesto_val, row_idx=row_idx, field_name="total_impuesto", errors=errors),
        "total_neto": _coerce_numeric(total_neto_val, row_idx=row_idx, field_name="total_neto", errors=errors),
        "resumen_id": _as_str_or_none(resumen_id_val),
        "cantidad_documentos": _coerce_int(cantidad_docs_val, row_idx=row_idx, field_name="cantidad_documentos", errors=errors),
    }

    required_fields = ["fecha_venta", "total_bruto", "total_impuesto", "total_neto"]
    if granularity == "transaction":
        required_fields.extend(["documento_numero", "hora_venta"])
    for field_name in required_fields:
        if not _has_value(normalized.get(field_name)):
            errors.append(f"row {row_idx}: falta '{field_name}' para granularity='{granularity}'")
    if granularity == "daily" and not _has_value(normalized.get("documento_numero")) and not _has_value(normalized.get("resumen_id")):
        errors.append(f"row {row_idx}: en granularity='daily' se requiere 'resumen_id' si no hay 'documento_numero'")
    return normalized


def _build_exporter_dedup_key(*, mall_id: str, local_id: str, granularity: str, normalized_row: Dict[str, Any]) -> str:
    if granularity == "daily":
        resumen_id = _as_str_or_none(normalized_row.get("resumen_id")) or "_"
        return "|".join([mall_id, local_id, "daily", str(normalized_row.get("fecha_venta") or ""), resumen_id])
    return "|".join([
        mall_id,
        local_id,
        "transaction",
        str(normalized_row.get("fecha_venta") or ""),
        _as_str_or_none(normalized_row.get("documento_tipo")) or "_",
        _as_str_or_none(normalized_row.get("documento_numero")) or "",
    ])


def _parse_exporter_rows(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    rows = payload.get("rows")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows debe ser un arreglo")
    meta = payload.get("meta") or {}
    if not isinstance(meta, dict):
        raise HTTPException(status_code=400, detail="meta debe ser un objeto")
    return rows, meta


def _process_exporter_sync_ingest_payload(payload: Dict[str, Any], svc: "TokenService", ctx: AuthContext) -> Dict[str, Any]:
    payload_mall_id = str(payload.get("mall_id") or "")
    payload_local_id = str(payload.get("local_id") or "")
    if not payload_mall_id or not payload_local_id:
        raise HTTPException(status_code=400, detail="mall_id y local_id son requeridos")
    validate_exporter_payload_mapping(payload_mall_id, payload_local_id, ctx)

    rows, meta = _parse_exporter_rows(payload)
    granularity = _normalize_granularity(meta.get("granularity"))
    batch_id = _as_str_or_none(meta.get("batch_id"))
    local_nombre: Optional[str] = None
    log_written = False

    def _write_webservice_log(
        *,
        estado: str,
        mensaje: str,
        records_processed: int,
        error_count: int,
        detalles: Optional[List[Dict[str, Any]]] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        nonlocal log_written
        svc.write_load_log(
            mall_id=payload_mall_id,
            local_id=payload_local_id,
            local_nombre=local_nombre,
            archivo=_exporter_log_filename(meta),
            estado=estado,
            mensaje=mensaje,
            batch_id=batch_id,
            detalles=detalles,
            records_processed=records_processed,
            error_count=error_count,
            metadata={
                "source": "exporter_sync_ingest",
                "granularity": granularity,
                "probe": bool(meta.get("probe")),
                "contract_type": _as_str_or_none(meta.get("contract_type")),
                **(extra_metadata or {}),
            },
        )
        log_written = True

    try:
        exporter_cfg_get = getattr(svc.store, "get_exporter_webservice_config", None)
        exporter_cfg = exporter_cfg_get(payload_mall_id, payload_local_id) if callable(exporter_cfg_get) else None
        if exporter_cfg:
            if exporter_cfg.get("enabled") is False:
                raise HTTPException(status_code=409, detail="Webservice exporter deshabilitado para este local en MsMall")
            if not _has_value(meta.get("granularity")) and _has_value(exporter_cfg.get("default_granularity")):
                granularity = _normalize_granularity(exporter_cfg.get("default_granularity"))
            if granularity == "transaction" and exporter_cfg.get("allow_transaction") is False:
                raise HTTPException(status_code=422, detail="Granularity 'transaction' no permitido para este local")
            if granularity == "daily" and exporter_cfg.get("allow_daily") is False:
                raise HTTPException(status_code=422, detail="Granularity 'daily' no permitido para este local")

        if not rows:
            response = {
                "accepted": True,
                "mall_id": payload_mall_id,
                "local_id": payload_local_id,
                "granularity": granularity,
                "webservice_config_applied": bool(exporter_cfg),
                "received": 0,
                "inserted": 0,
                "updated": 0,
                "ventas_inserted": 0,
                "ventas_updated": 0,
                "probe": bool(meta.get("probe")),
                "batch_id": batch_id,
            }
            _write_webservice_log(
                estado="exito",
                mensaje="Carga vía WebService recibida correctamente. 0 registros procesados.",
                records_processed=0,
                error_count=0,
                extra_metadata=response,
            )
            return response

        local_info = getattr(svc.store, "get_local_exporter_code", lambda *_: None)(payload_mall_id, payload_local_id)
        if not local_info:
            raise HTTPException(status_code=422, detail="Local no encontrado en MsMall para mall_id/local_id")
        local_nombre = _as_str_or_none(local_info.get("local_nombre") or local_info.get("nombre"))
        codigo_cliente = _as_str_or_none(local_info.get("codigo_cliente") or local_info.get("codigo_interno"))
        if not codigo_cliente:
            raise HTTPException(status_code=422, detail="El local existe pero no tiene codigo_interno configurado en MsMall")

        errors: List[str] = []
        persist_rows: List[Dict[str, Any]] = []
        contract_type = (
            _as_str_or_none(meta.get("contract_type"))
            or _as_str_or_none((exporter_cfg or {}).get("contract_type"))
            or "msmall_sales_v1"
        )
        chunk_index = _coerce_int(meta.get("chunk_index"), row_idx=0, field_name="chunk_index", errors=[])
        chunk_total = _coerce_int(meta.get("chunk_total"), row_idx=0, field_name="chunk_total", errors=[])

        for idx, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                errors.append(f"row {idx}: cada elemento de rows debe ser objeto")
                continue
            normalized = _canonicalize_exporter_row(row, row_idx=idx, granularity=granularity, errors=errors)
            persist_rows.append({
                "mall_id": payload_mall_id,
                "local_id": payload_local_id,
                "codigo_cliente": codigo_cliente,
                "contract_type": contract_type,
                "granularity": granularity,
                "batch_id": batch_id,
                "chunk_index": chunk_index,
                "chunk_total": chunk_total,
                "row_index": idx,
                "dedup_key": _build_exporter_dedup_key(mall_id=payload_mall_id, local_id=payload_local_id, granularity=granularity, normalized_row=normalized),
                "documento_tipo": normalized.get("documento_tipo"),
                "documento_numero": normalized.get("documento_numero"),
                "resumen_id": normalized.get("resumen_id"),
                "cantidad_documentos": normalized.get("cantidad_documentos"),
                "fecha_venta": normalized.get("fecha_venta"),
                "hora_venta": normalized.get("hora_venta"),
                "total_bruto": normalized.get("total_bruto"),
                "total_impuesto": normalized.get("total_impuesto"),
                "total_neto": normalized.get("total_neto"),
                "raw_row": row,
                "raw_meta": meta,
            })

        if errors:
            details = "; ".join(errors[:10])
            if len(errors) > 10:
                details += f" (+{len(errors) - 10} mas)"
            _write_webservice_log(
                estado="error",
                mensaje=f"Carga vía WebService rechazada por validación. {len(errors)} errores detectados.",
                records_processed=0,
                error_count=len(errors),
                detalles=_exporter_validation_details(errors),
                extra_metadata={"validation_errors": errors[:20]},
            )
            raise HTTPException(status_code=422, detail=f"Payload exporter invalido: {details}")

        upsert_result = getattr(svc.store, "upsert_exporter_ingest_rows", None)
        if not callable(upsert_result):
            raise HTTPException(status_code=500, detail="Store no soporta persistencia de ingest exporter")
        stats = upsert_result(persist_rows) or {}
        inserted = int(stats.get("inserted") or 0)
        updated = int(stats.get("updated") or 0)
        promoter = getattr(svc.store, "promote_exporter_ingest_rows", None)
        if not callable(promoter):
            raise HTTPException(status_code=500, detail="Store no soporta promocion de ventas exporter")
        try:
            sales_stats = promoter(persist_rows) or {}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"No se pudo promover a ventas: {exc}") from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "Exporter sales promotion failed mall=%s local=%s batch=%s: %s",
                payload_mall_id,
                payload_local_id,
                batch_id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Error promoviendo ventas WebService a public.ventas: {exc}",
            ) from exc
        ventas_inserted = int(sales_stats.get("inserted") or 0)
        ventas_updated = int(sales_stats.get("updated") or 0)
        response = {
            "accepted": True,
            "mall_id": payload_mall_id,
            "local_id": payload_local_id,
            "codigo_cliente": codigo_cliente,
            "granularity": granularity,
            "webservice_config_applied": bool(exporter_cfg),
            "received": len(rows),
            "inserted": inserted,
            "updated": updated,
            "ventas_inserted": ventas_inserted,
            "ventas_updated": ventas_updated,
            "batch_id": batch_id,
        }
        _write_webservice_log(
            estado="exito",
            mensaje=(
                f"Carga vía WebService completada. {len(rows)} registros procesados. "
                f"Ventas: {ventas_inserted} nuevas, {ventas_updated} actualizadas."
            ),
            records_processed=len(rows),
            error_count=0,
            extra_metadata={**response, "staging_inserted": inserted, "staging_updated": updated},
        )
        return response
    except HTTPException as exc:
        if not log_written:
            svc.write_load_log(
                mall_id=payload_mall_id,
                local_id=payload_local_id,
                local_nombre=local_nombre,
                archivo=_exporter_log_filename(meta),
                estado="error",
                mensaje=f"Carga vía WebService falló: {exc.detail}",
                batch_id=batch_id,
                records_processed=0,
                error_count=1,
                metadata={
                    "source": "exporter_sync_ingest",
                    "granularity": granularity,
                    "detail": str(exc.detail),
                    "status_code": exc.status_code,
                },
            )
        raise
    except Exception as exc:
        if not log_written:
            svc.write_load_log(
                mall_id=payload_mall_id,
                local_id=payload_local_id,
                local_nombre=local_nombre,
                archivo=_exporter_log_filename(meta),
                estado="error",
                mensaje=f"Carga vía WebService falló por error interno: {exc}",
                batch_id=batch_id,
                records_processed=0,
                error_count=1,
                metadata={
                    "source": "exporter_sync_ingest",
                    "granularity": granularity,
                    "detail": str(exc),
                },
            )
        raise


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


def sanitize_exporter_webservice_config_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return row
    safe = dict(row)
    if safe.get("default_granularity"):
        safe["default_granularity"] = _normalize_granularity(safe.get("default_granularity"))
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
            access_never_expires=request_explicit_never_expires(payload),
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

    @router.get("/api/v1/exporter/configs")
    async def list_exporter_webservice_configs(
        mall_id: Optional[str] = None,
        local_id: Optional[str] = None,
        enabled: Optional[bool] = None,
        _: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        lister = getattr(svc.store, "list_exporter_webservice_configs", None)
        if not callable(lister):
            raise HTTPException(status_code=500, detail="Store no soporta configuracion exporter webservice")
        rows = lister({"mall_id": mall_id, "local_id": local_id, "enabled": enabled})
        return [sanitize_exporter_webservice_config_row(row) for row in rows]

    @router.get("/api/v1/exporter/configs/{local_id}")
    async def get_exporter_webservice_config(
        local_id: str,
        mall_id: str,
        _: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        getter = getattr(svc.store, "get_exporter_webservice_config", None)
        if not callable(getter):
            raise HTTPException(status_code=500, detail="Store no soporta configuracion exporter webservice")
        row = getter(mall_id, local_id)
        if not row:
            raise HTTPException(status_code=404, detail="Configuracion exporter webservice no encontrada")
        return sanitize_exporter_webservice_config_row(row)

    @router.put("/api/v1/exporter/configs/{local_id}")
    async def put_exporter_webservice_config(
        local_id: str,
        payload: UpsertExporterWebserviceConfigRequest,
        ctx: AuthContext = Depends(require_token_auth("tokens:manage")),
        svc: TokenService = Depends(get_token_service),
    ):
        upserter = getattr(svc.store, "upsert_exporter_webservice_config", None)
        if not callable(upserter):
            raise HTTPException(status_code=500, detail="Store no soporta configuracion exporter webservice")
        row = upserter({
            "mall_id": payload.mall_id,
            "local_id": local_id,
            "enabled": payload.enabled,
            "contract_type": payload.contract_type,
            "default_granularity": _normalize_granularity(payload.default_granularity),
            "allow_transaction": payload.allow_transaction,
            "allow_daily": payload.allow_daily,
            "strict_validation": payload.strict_validation,
            "notes": payload.notes.strip() if payload.notes else None,
            "updated_by": ctx.token_id,
        })
        if not row:
            raise HTTPException(status_code=500, detail="No se pudo guardar la configuracion exporter webservice")
        return sanitize_exporter_webservice_config_row(row)

    @router.post("/api/v1/exporter/sync/ingest")
    async def exporter_sync_ingest(
        payload: Dict[str, Any],
        ctx: AuthContext = Depends(require_token_auth("export:write", token_types={TOKEN_TYPE_EXPORTER})),
        svc: TokenService = Depends(get_token_service),
    ):
        return _process_exporter_sync_ingest_payload(payload, svc, ctx)

    return router

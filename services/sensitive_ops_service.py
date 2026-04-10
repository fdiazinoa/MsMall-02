import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


def mask_secret(value: Optional[Any]) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 2:
        return "*" * len(text)
    if len(text) <= 4:
        return f"{text[0]}***{text[-1]}"
    return f"{text[:2]}***{text[-2:]}"


def sanitize_remote_connection_record(row: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(row or {})
    raw_password = str(data.get("password") or "")
    data["password"] = ""  # Never expose secrets in clear text.
    data["password_masked"] = mask_secret(raw_password) if raw_password else ""
    data["has_password"] = bool(raw_password)
    return data


def sanitize_error_text(value: Any, max_len: int = 400) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*([^\s,;]+)", r"\1=[REDACTED]", text)
    if len(text) > max_len:
        return f"{text[:max_len-3]}..."
    return text


class SensitiveOpsService:
    def __init__(self, supabase_client: Any, logger: Any):
        self.supabase = supabase_client
        self.logger = logger

    def _require_supabase(self) -> None:
        if not self.supabase:
            raise RuntimeError("Supabase no configurado")

    def _insert_audit_log(
        self,
        *,
        user_id: Optional[str],
        mall_id: Optional[str],
        action: str,
        detail: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.supabase:
            return
        try:
            self.supabase.table("system_audit_logs").insert({
                "usuario_id": user_id,
                "mall_id": mall_id,
                "accion": action,
                "detalle": detail,
                "metadata": {
                    **(metadata or {}),
                    "timestamp": datetime.now().isoformat(),
                },
            }).execute()
        except Exception as audit_err:
            self.logger.warning(f"Audit log failed (non-critical): {sanitize_error_text(audit_err)}")

    def _get_remote_connection_by_id(self, connection_id: str) -> Optional[Dict[str, Any]]:
        self._require_supabase()
        res = (
            self.supabase.table("remote_connections")
            .select("*")
            .eq("id", connection_id)
            .maybe_single()
            .execute()
        )
        return res.data if res else None

    def list_remote_connections(
        self,
        *,
        mall_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> List[Dict[str, Any]]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        res = (
            self.supabase.table("remote_connections")
            .select("*")
            .eq("mall_id", mall_id)
            .order("nombre", desc=False)
            .execute()
        )
        return [sanitize_remote_connection_record(row) for row in (res.data or [])]

    def create_remote_connection(
        self,
        *,
        payload: Dict[str, Any],
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        mall_id = payload.get("mall_id")
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        if not str(payload.get("password") or "").strip():
            raise ValueError("password es requerido")

        res = (
            self.supabase.table("remote_connections")
            .insert(payload)
            .select()
            .single()
            .execute()
        )
        record = sanitize_remote_connection_record(res.data or {})
        self._insert_audit_log(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="REMOTE_CONNECTION_CREATE",
            detail=f"Created remote connection '{payload.get('nombre')}'",
            metadata={"connection_id": (res.data or {}).get("id")},
        )
        return record

    def update_remote_connection(
        self,
        *,
        connection_id: str,
        payload: Dict[str, Any],
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        existing = self._get_remote_connection_by_id(connection_id)
        if not existing:
            raise KeyError("Conexión remota no encontrada")
        mall_id = existing.get("mall_id")
        ensure_operator_can_access_mall(operator_ctx, mall_id)

        update_payload = dict(payload or {})
        if "password" in update_payload:
            pwd = str(update_payload.get("password") or "").strip()
            if not pwd:
                # Preserve existing password when frontend intentionally omits/clears masked value.
                update_payload.pop("password", None)
        if not update_payload:
            return sanitize_remote_connection_record(existing)

        res = (
            self.supabase.table("remote_connections")
            .update(update_payload)
            .eq("id", connection_id)
            .select()
            .single()
            .execute()
        )
        record = sanitize_remote_connection_record(res.data or {})
        self._insert_audit_log(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="REMOTE_CONNECTION_UPDATE",
            detail=f"Updated remote connection '{(res.data or {}).get('nombre') or existing.get('nombre')}'",
            metadata={"connection_id": connection_id, "updated_fields": sorted(update_payload.keys())},
        )
        return record

    def delete_remote_connection(
        self,
        *,
        connection_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> None:
        self._require_supabase()
        existing = self._get_remote_connection_by_id(connection_id)
        if not existing:
            raise KeyError("Conexión remota no encontrada")
        mall_id = existing.get("mall_id")
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        self.supabase.table("remote_connections").delete().eq("id", connection_id).execute()
        self._insert_audit_log(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="REMOTE_CONNECTION_DELETE",
            detail=f"Deleted remote connection '{existing.get('nombre')}'",
            metadata={"connection_id": connection_id},
        )

    def list_load_logs(
        self,
        *,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
        mall_id: str,
        local_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)
        safe_limit = max(1, min(int(limit or 50), 200))

        primary_error: Optional[Exception] = None
        primary_rows: List[Dict[str, Any]] = []
        try:
            query = self.supabase.table("logs_carga").select("*").eq("mall_id", mall_id)
            if local_id:
                query = query.eq("local_id", local_id)
            if start_date:
                query = query.gte("fecha_hora", f"{start_date}T00:00:00")
            if end_date:
                query = query.lte("fecha_hora", f"{end_date}T23:59:59")
            res = query.order("fecha_hora", desc=True).limit(safe_limit).execute()
            primary_rows = res.data or []
        except Exception as err:
            primary_error = err

        if primary_error is not None:
            err_msg = sanitize_error_text(primary_error)
            self.logger.warning(f"logs_carga primary query fallback: {err_msg}")

        if local_id:
            stores_query = self.supabase.table("locales").select("id, nombre").eq("mall_id", mall_id).eq("id", local_id)
        else:
            stores_query = self.supabase.table("locales").select("id, nombre").eq("mall_id", mall_id)
        stores_res = stores_query.execute()
        stores = stores_res.data or []
        store_names = [s.get("nombre") for s in stores if s.get("nombre")]
        store_ids = {s.get("id") for s in stores if s.get("id")}
        if not store_names:
            return primary_rows

        legacy_query = self.supabase.table("logs_carga").select("*").in_("local_nombre", store_names)
        if start_date:
            legacy_query = legacy_query.gte("fecha_hora", f"{start_date}T00:00:00")
        if end_date:
            legacy_query = legacy_query.lte("fecha_hora", f"{end_date}T23:59:59")
        legacy_res = legacy_query.order("fecha_hora", desc=True).limit(safe_limit).execute()
        legacy_rows = legacy_res.data or []

        filtered_legacy_rows: List[Dict[str, Any]] = []
        for row in legacy_rows:
            row_mall_id = row.get("mall_id")
            row_local_id = row.get("local_id")
            if row_mall_id and row_mall_id != mall_id:
                continue
            if local_id and row_local_id and row_local_id != local_id:
                continue
            if row_local_id and store_ids and row_local_id not in store_ids:
                continue
            filtered_legacy_rows.append(row)

        merged: Dict[str, Dict[str, Any]] = {}
        for row in [*primary_rows, *filtered_legacy_rows]:
            row_id = str(
                row.get("id")
                or f"{row.get('fecha_hora')}::{row.get('local_id') or row.get('local_nombre')}::{row.get('archivo')}::{row.get('estado')}"
            )
            merged[row_id] = dict(row)

        return sorted(
            merged.values(),
            key=lambda item: str(item.get("fecha_hora") or ""),
            reverse=True,
        )[:safe_limit]

    def clear_load_logs(
        self,
        *,
        mall_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        ensure_operator_can_access_mall(operator_ctx, mall_id)

        stores_res = self.supabase.table("locales").select("id, nombre").eq("mall_id", mall_id).execute()
        stores = stores_res.data or []
        store_ids = [s.get("id") for s in stores if s.get("id")]
        store_names = [s.get("nombre") for s in stores if s.get("nombre")]

        if not store_ids and not store_names:
            return {"status": "success", "message": "No hay locales asociados al mall seleccionado.", "deleted_count": 0}

        deleted_count = 0
        try:
            delete_by_mall = self.supabase.table("logs_carga").delete().eq("mall_id", mall_id).execute()
            deleted_count += len(delete_by_mall.data or [])

            if store_ids:
                legacy_by_local = (
                    self.supabase.table("logs_carga")
                    .delete()
                    .is_("mall_id", "null")
                    .in_("local_id", store_ids)
                    .execute()
                )
                deleted_count += len(legacy_by_local.data or [])

            if store_names:
                legacy_by_name = (
                    self.supabase.table("logs_carga")
                    .delete()
                    .is_("mall_id", "null")
                    .is_("local_id", "null")
                    .in_("local_nombre", store_names)
                    .execute()
                )
                deleted_count += len(legacy_by_name.data or [])
        except Exception:
            if store_names:
                legacy_delete = self.supabase.table("logs_carga").delete().in_("local_nombre", store_names).execute()
                deleted_count += len(legacy_delete.data or [])

        self._insert_audit_log(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="LOAD_LOGS_CLEANUP",
            detail=f"Cleared load logs for mall {mall_id}",
            metadata={"deleted_count": deleted_count},
        )
        return {
            "status": "success",
            "message": "Historial de auditoría limpiado correctamente.",
            "deleted_count": deleted_count,
        }

    def reactivate_local_processing(
        self,
        *,
        local_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_supabase()
        res = self.supabase.table("locales").select("id, mall_id, nombre").eq("id", local_id).maybe_single().execute()
        local_row = res.data if res else None
        if not local_row:
            raise KeyError("Local no encontrado")
        mall_id = local_row.get("mall_id")
        ensure_operator_can_access_mall(operator_ctx, mall_id)

        (
            self.supabase.table("locales")
            .update({"processing_status": "IDLE", "consecutive_failures": 0})
            .eq("id", local_id)
            .execute()
        )

        update_res = (
            self.supabase.table("locales")
            .select("id, processing_status, consecutive_failures")
            .eq("id", local_id)
            .single()
            .execute()
        )

        self._insert_audit_log(
            user_id=operator_ctx.get("user_id"),
            mall_id=mall_id,
            action="LOCAL_REACTIVATE_PROCESSING",
            detail=f"Reactivated processing for local '{local_row.get('nombre')}'",
            metadata={"local_id": local_id},
        )
        return {
            "status": "success",
            "message": "Local reactivado correctamente.",
            "local": update_res.data or {"id": local_id, "processing_status": "IDLE", "consecutive_failures": 0},
        }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException

from analytics import generate_sales_cube


VALID_DATA_TYPES = {"text", "number", "date", "select"}
VALID_WIDGET_TYPES = {"textbox", "select", "drilldown"}
EMPTY_GROUP_LABEL = "Sin valor"


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _serialize_number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Valor numérico inválido para campo libre.")


def _serialize_date(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = _clean_text(value)
    if not text:
        return None
    try:
        return pd.to_datetime(text).date().isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="Valor de fecha inválido para campo libre.")


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "on"}


def _normalize_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_definition_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    normalized["key"] = _clean_text(normalized.get("key"))
    normalized["label"] = _clean_text(normalized.get("label"))
    normalized["data_type"] = (_clean_text(normalized.get("data_type")) or "").lower()
    normalized["widget_type"] = (_clean_text(normalized.get("widget_type")) or "").lower()
    normalized["required"] = _normalize_bool(normalized.get("required"), default=False)
    normalized["active"] = _normalize_bool(normalized.get("active"), default=True)
    normalized["sort_order"] = _normalize_int(normalized.get("sort_order"), default=0)
    normalized["parent_field_id"] = normalized.get("parent_field_id") or None
    normalized["mall_id"] = normalized.get("mall_id")
    normalized["options"] = list(normalized.get("options") or [])
    return normalized


def _normalize_option_payload(payload: Dict[str, Any], field_definition_id: Optional[str] = None) -> Dict[str, Any]:
    normalized = dict(payload or {})
    normalized["id"] = normalized.get("id") or None
    normalized["field_definition_id"] = field_definition_id or normalized.get("field_definition_id")
    normalized["label"] = _clean_text(normalized.get("label"))
    normalized["value"] = _clean_text(normalized.get("value"))
    normalized["sort_order"] = _normalize_int(normalized.get("sort_order"), default=0)
    normalized["active"] = _normalize_bool(normalized.get("active"), default=True)
    normalized["parent_option_id"] = normalized.get("parent_option_id") or None
    return normalized


def _normalize_value_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    normalized["field_definition_id"] = normalized.get("field_definition_id")
    normalized["value_text"] = _clean_text(normalized.get("value_text"))
    normalized["value_number"] = normalized.get("value_number")
    normalized["value_date"] = normalized.get("value_date")
    normalized["selected_option_id"] = normalized.get("selected_option_id") or None
    return normalized


@dataclass
class LocalCustomFieldSnapshot:
    definitions: List[Dict[str, Any]]
    definitions_by_key: Dict[str, Dict[str, Any]]
    values_by_local: Dict[str, Dict[str, Dict[str, Any]]]


class LocalCustomFieldsService:
    def __init__(self, supabase_client, logger):
        self.supabase = supabase_client
        self.logger = logger

    def _require_db(self):
        if not self.supabase:
            raise HTTPException(status_code=500, detail="Supabase no configurado")

    def _ensure_key_available(self, mall_id: str, key: str, field_id: Optional[str] = None) -> None:
        existing = (
            self.supabase.table("local_custom_field_definitions")
            .select("id")
            .eq("mall_id", mall_id)
            .eq("key", key)
            .maybe_single()
            .execute()
        )
        row = existing.data
        if row and row.get("id") != field_id:
            raise HTTPException(status_code=409, detail="Ya existe un campo libre con esa clave en este mall.")

    def _load_definition(self, field_id: str) -> Dict[str, Any]:
        res = (
            self.supabase.table("local_custom_field_definitions")
            .select("*")
            .eq("id", field_id)
            .maybe_single()
            .execute()
        )
        row = res.data
        if not row:
            raise HTTPException(status_code=404, detail="Campo libre no encontrado.")
        return row

    def _load_local(self, local_id: str) -> Dict[str, Any]:
        res = (
            self.supabase.table("locales")
            .select("id, mall_id, nombre")
            .eq("id", local_id)
            .maybe_single()
            .execute()
        )
        row = res.data
        if not row:
            raise HTTPException(status_code=404, detail="Local no encontrado.")
        return row

    def _validate_definition(self, payload: Dict[str, Any], existing_field_id: Optional[str] = None) -> Dict[str, Any]:
        data = _normalize_definition_payload(payload)
        if not data.get("mall_id"):
            raise HTTPException(status_code=400, detail="mall_id es requerido para el campo libre.")
        if not data.get("key"):
            raise HTTPException(status_code=400, detail="La clave técnica del campo libre es requerida.")
        if not data.get("label"):
            raise HTTPException(status_code=400, detail="La etiqueta del campo libre es requerida.")
        if data["data_type"] not in VALID_DATA_TYPES:
            raise HTTPException(status_code=400, detail="Tipo de dato inválido para campo libre.")
        if data["widget_type"] not in VALID_WIDGET_TYPES:
            raise HTTPException(status_code=400, detail="Tipo de control inválido para campo libre.")
        if data["widget_type"] == "textbox" and data["data_type"] == "select":
            raise HTTPException(status_code=400, detail="Los campos de selección no usan widget textbox.")
        if data["widget_type"] in {"select", "drilldown"} and data["data_type"] != "select":
            raise HTTPException(status_code=400, detail="Los widgets select/drilldown requieren tipo de dato select.")
        if data["widget_type"] != "drilldown":
            data["parent_field_id"] = None
        elif not data.get("parent_field_id"):
            raise HTTPException(status_code=400, detail="Un campo drilldown debe tener un campo padre.")
        self._ensure_key_available(data["mall_id"], data["key"], field_id=existing_field_id)
        return data

    def _validate_options(
        self,
        definition: Dict[str, Any],
        options: Sequence[Dict[str, Any]],
        parent_field_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        normalized_options = [_normalize_option_payload(opt, field_definition_id=definition["id"]) for opt in options]
        if definition["widget_type"] == "textbox":
            return []

        if not normalized_options:
            raise HTTPException(status_code=400, detail="Los campos select/drilldown requieren al menos una opción.")

        seen_values = set()
        seen_ids = set()
        parent_option_ids = set()
        if parent_field_id:
            parent_rows = (
                self.supabase.table("local_custom_field_options")
                .select("id")
                .eq("field_definition_id", parent_field_id)
                .execute()
            ).data or []
            parent_option_ids = {row.get("id") for row in parent_rows if row.get("id")}

        for option in normalized_options:
            if not option["label"] or not option["value"]:
                raise HTTPException(status_code=400, detail="Cada opción debe tener etiqueta y valor.")
            key = option["value"].lower()
            if key in seen_values:
                raise HTTPException(status_code=409, detail="No puede repetir valores de opción en el mismo campo.")
            seen_values.add(key)
            if option["id"]:
                if option["id"] in seen_ids:
                    raise HTTPException(status_code=409, detail="ID de opción repetido en la actualización.")
                seen_ids.add(option["id"])
            if definition["widget_type"] == "drilldown":
                if not option.get("parent_option_id"):
                    raise HTTPException(status_code=400, detail="Cada opción drilldown debe apuntar a una opción padre.")
                if parent_option_ids and option["parent_option_id"] not in parent_option_ids:
                    raise HTTPException(status_code=400, detail="La opción hija referencia una opción padre inválida.")
            else:
                option["parent_option_id"] = None

        return normalized_options

    def _replace_options(self, field_definition: Dict[str, Any], options: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        definition_id = field_definition["id"]
        existing = (
            self.supabase.table("local_custom_field_options")
            .select("*")
            .eq("field_definition_id", definition_id)
            .execute()
        ).data or []
        existing_by_id = {row["id"]: row for row in existing if row.get("id")}

        if field_definition["widget_type"] == "textbox":
            for row in existing:
                if row.get("id"):
                    (
                        self.supabase.table("local_custom_field_options")
                        .delete()
                        .eq("id", row["id"])
                        .execute()
                    )
            return []

        normalized = self._validate_options(field_definition, options, field_definition.get("parent_field_id"))
        keep_ids = set()
        for option in normalized:
            payload = {
                "field_definition_id": definition_id,
                "label": option["label"],
                "value": option["value"],
                "sort_order": option["sort_order"],
                "active": option["active"],
                "parent_option_id": option["parent_option_id"],
            }
            option_id = option.get("id")
            if option_id and option_id in existing_by_id:
                (
                    self.supabase.table("local_custom_field_options")
                    .update(payload)
                    .eq("id", option_id)
                    .execute()
                )
                keep_ids.add(option_id)
            else:
                payload["id"] = option_id or str(uuid4())
                (
                    self.supabase.table("local_custom_field_options")
                    .insert(payload)
                    .execute()
                )
                keep_ids.add(payload["id"])

        for row in existing:
            if row.get("id") and row["id"] not in keep_ids:
                (
                    self.supabase.table("local_custom_field_options")
                    .delete()
                    .eq("id", row["id"])
                    .execute()
                )

        return self._list_options_for_field(definition_id)

    def _list_options_for_field(self, definition_id: str) -> List[Dict[str, Any]]:
        rows = (
            self.supabase.table("local_custom_field_options")
            .select("*")
            .eq("field_definition_id", definition_id)
            .order("sort_order")
            .execute()
        ).data or []
        return rows

    def list_definitions(self, mall_id: str, include_inactive: bool = True) -> List[Dict[str, Any]]:
        self._require_db()
        query = (
            self.supabase.table("local_custom_field_definitions")
            .select("*")
            .eq("mall_id", mall_id)
            .order("sort_order")
        )
        if not include_inactive:
            query = query.eq("active", True)
        definitions = query.execute().data or []
        if not definitions:
            return []
        field_ids = [row["id"] for row in definitions if row.get("id")]
        options = []
        if field_ids:
            options = (
                self.supabase.table("local_custom_field_options")
                .select("*")
                .in_("field_definition_id", field_ids)
                .order("sort_order")
                .execute()
            ).data or []
        options_by_field: Dict[str, List[Dict[str, Any]]] = {}
        for option in options:
            options_by_field.setdefault(option.get("field_definition_id"), []).append(option)
        enriched = []
        for definition in definitions:
            row = dict(definition)
            row["options"] = options_by_field.get(definition["id"], [])
            enriched.append(row)
        return enriched

    def create_definition(
        self,
        payload: Dict[str, Any],
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_db()
        definition = self._validate_definition(payload)
        ensure_operator_can_access_mall(operator_ctx, definition["mall_id"])

        definition_id = str(uuid4())
        insert_payload = {
            "id": definition_id,
            "mall_id": definition["mall_id"],
            "key": definition["key"],
            "label": definition["label"],
            "data_type": definition["data_type"],
            "widget_type": definition["widget_type"],
            "required": definition["required"],
            "active": definition["active"],
            "sort_order": definition["sort_order"],
            "parent_field_id": definition["parent_field_id"],
        }
        (
            self.supabase.table("local_custom_field_definitions")
            .insert(insert_payload)
            .execute()
        )
        field_row = self._load_definition(definition_id)
        options = self._replace_options(field_row, definition.get("options") or [])
        field_row["options"] = options
        return field_row

    def update_definition(
        self,
        field_id: str,
        payload: Dict[str, Any],
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_db()
        existing = self._load_definition(field_id)
        ensure_operator_can_access_mall(operator_ctx, existing.get("mall_id"))

        merged = dict(existing)
        merged.update({k: v for k, v in payload.items() if v is not None})
        validated = self._validate_definition(merged, existing_field_id=field_id)
        update_payload = {
            "key": validated["key"],
            "label": validated["label"],
            "data_type": validated["data_type"],
            "widget_type": validated["widget_type"],
            "required": validated["required"],
            "active": validated["active"],
            "sort_order": validated["sort_order"],
            "parent_field_id": validated["parent_field_id"],
        }
        (
            self.supabase.table("local_custom_field_definitions")
            .update(update_payload)
            .eq("id", field_id)
            .execute()
        )
        field_row = self._load_definition(field_id)
        field_row["options"] = self._replace_options(field_row, validated.get("options") or [])
        return field_row

    def _serialize_value_for_definition(
        self,
        definition: Dict[str, Any],
        payload: Dict[str, Any],
        options_by_id: Dict[str, Dict[str, Any]],
        selected_parent_option_ids: Dict[str, str]
    ) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
        data_type = definition["data_type"]
        widget_type = definition["widget_type"]
        serialized = {
            "value_text": None,
            "value_number": None,
            "value_date": None,
            "selected_option_id": None,
        }
        display_value = None
        filter_value = None

        if data_type == "text":
            serialized["value_text"] = _clean_text(payload.get("value_text"))
            display_value = serialized["value_text"]
            filter_value = serialized["value_text"]
        elif data_type == "number":
            serialized["value_number"] = _serialize_number(payload.get("value_number"))
            display_value = None if serialized["value_number"] is None else str(serialized["value_number"])
            filter_value = display_value
        elif data_type == "date":
            serialized["value_date"] = _serialize_date(payload.get("value_date"))
            display_value = serialized["value_date"]
            filter_value = serialized["value_date"]
        elif data_type == "select":
            selected_option_id = payload.get("selected_option_id")
            if selected_option_id:
                option = options_by_id.get(selected_option_id)
                if not option or option.get("field_definition_id") != definition["id"]:
                    raise HTTPException(status_code=400, detail=f"Opción inválida para el campo {definition['label']}.")
                if widget_type == "drilldown":
                    parent_field_id = definition.get("parent_field_id")
                    expected_parent_option_id = selected_parent_option_ids.get(parent_field_id)
                    if expected_parent_option_id and option.get("parent_option_id") != expected_parent_option_id:
                        raise HTTPException(status_code=400, detail=f"La selección de {definition['label']} no corresponde con el campo padre.")
                serialized["selected_option_id"] = selected_option_id
                display_value = option.get("label") or option.get("value")
                filter_value = option.get("value") or option.get("label")
            else:
                serialized["selected_option_id"] = None
        return serialized, display_value, filter_value

    def get_local_fields(
        self,
        local_id: str,
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
        include_inactive: bool = False,
    ) -> Dict[str, Any]:
        self._require_db()
        local_row = self._load_local(local_id)
        ensure_operator_can_access_mall(operator_ctx, local_row.get("mall_id"))
        definitions = self.list_definitions(local_row["mall_id"], include_inactive=include_inactive)
        if not definitions:
            return {"local_id": local_id, "mall_id": local_row["mall_id"], "definitions": [], "values": []}

        field_ids = [row["id"] for row in definitions]
        values = (
            self.supabase.table("local_custom_field_values")
            .select("*")
            .eq("local_id", local_id)
            .in_("field_definition_id", field_ids)
            .execute()
        ).data or []
        value_by_field = {row["field_definition_id"]: row for row in values}
        options_by_id = {
            opt["id"]: opt
            for definition in definitions
            for opt in definition.get("options", [])
            if opt.get("id")
        }

        enriched_values = []
        for definition in definitions:
            row = value_by_field.get(definition["id"])
            display_value = None
            filter_value = None
            if row:
                if definition["data_type"] == "text":
                    display_value = row.get("value_text")
                    filter_value = display_value
                elif definition["data_type"] == "number":
                    display_value = row.get("value_number")
                    filter_value = display_value
                elif definition["data_type"] == "date":
                    raw_date = row.get("value_date")
                    display_value = raw_date.isoformat() if hasattr(raw_date, "isoformat") else raw_date
                    filter_value = display_value
                elif definition["data_type"] == "select":
                    option = options_by_id.get(row.get("selected_option_id"))
                    display_value = (option or {}).get("label")
                    filter_value = (option or {}).get("value")
            enriched_values.append({
                "field_definition_id": definition["id"],
                "value_text": row.get("value_text") if row else None,
                "value_number": row.get("value_number") if row else None,
                "value_date": (
                    row.get("value_date").isoformat()
                    if row and hasattr(row.get("value_date"), "isoformat")
                    else (row.get("value_date") if row else None)
                ),
                "selected_option_id": row.get("selected_option_id") if row else None,
                "display_value": display_value,
                "filter_value": filter_value,
            })
        return {
            "local_id": local_id,
            "mall_id": local_row["mall_id"],
            "definitions": definitions,
            "values": enriched_values,
        }

    def upsert_local_values(
        self,
        local_id: str,
        payload: Sequence[Dict[str, Any]],
        operator_ctx: Dict[str, Any],
        ensure_operator_can_access_mall: Callable[[Dict[str, Any], Optional[str]], None],
    ) -> Dict[str, Any]:
        self._require_db()
        local_row = self._load_local(local_id)
        ensure_operator_can_access_mall(operator_ctx, local_row.get("mall_id"))
        definitions = self.list_definitions(local_row["mall_id"], include_inactive=True)
        definitions_by_id = {row["id"]: row for row in definitions}
        existing_values = (
            self.supabase.table("local_custom_field_values")
            .select("*")
            .eq("local_id", local_id)
            .execute()
        ).data or []
        existing_by_field = {row["field_definition_id"]: row for row in existing_values}
        input_by_field = {
            value["field_definition_id"]: _normalize_value_payload(value)
            for value in payload
            if value.get("field_definition_id")
        }
        options_by_id = {
            opt["id"]: opt
            for definition in definitions
            for opt in definition.get("options", [])
            if opt.get("id")
        }
        selected_parent_option_ids: Dict[str, str] = {}
        ordered_definitions = sorted(definitions, key=lambda row: (row.get("sort_order", 0), row.get("label", "")))

        for definition in ordered_definitions:
            candidate = input_by_field.get(definition["id"], {})
            serialized, _display_value, _filter_value = self._serialize_value_for_definition(
                definition,
                candidate,
                options_by_id,
                selected_parent_option_ids,
            )
            is_empty = all(serialized.get(key) in (None, "") for key in serialized)
            if definition.get("required") and definition.get("active") and is_empty:
                raise HTTPException(status_code=400, detail=f"El campo libre '{definition['label']}' es requerido.")

            if definition["widget_type"] in {"select", "drilldown"} and serialized.get("selected_option_id"):
                selected_parent_option_ids[definition["id"]] = serialized["selected_option_id"]

            existing = existing_by_field.get(definition["id"])
            if is_empty:
                if existing:
                    (
                        self.supabase.table("local_custom_field_values")
                        .delete()
                        .eq("id", existing["id"])
                        .execute()
                    )
                continue

            record_payload = {
                "local_id": local_id,
                "field_definition_id": definition["id"],
                **serialized,
            }
            if existing:
                (
                    self.supabase.table("local_custom_field_values")
                    .update(record_payload)
                    .eq("id", existing["id"])
                    .execute()
                )
            else:
                record_payload["id"] = str(uuid4())
                (
                    self.supabase.table("local_custom_field_values")
                    .insert(record_payload)
                    .execute()
                )

        return self.get_local_fields(local_id, operator_ctx, ensure_operator_can_access_mall, include_inactive=True)

    def build_snapshot(
        self,
        mall_id: str,
        local_ids: Sequence[str],
        include_inactive: bool = False,
    ) -> LocalCustomFieldSnapshot:
        definitions = self.list_definitions(mall_id, include_inactive=include_inactive)
        definitions_by_key = {definition["key"]: definition for definition in definitions}
        if not definitions or not local_ids:
            return LocalCustomFieldSnapshot(definitions=definitions, definitions_by_key=definitions_by_key, values_by_local={})

        field_ids = [definition["id"] for definition in definitions]
        values = (
            self.supabase.table("local_custom_field_values")
            .select("*")
            .in_("local_id", list(local_ids))
            .in_("field_definition_id", field_ids)
            .execute()
        ).data or []
        options_by_id = {
            opt["id"]: opt
            for definition in definitions
            for opt in definition.get("options", [])
            if opt.get("id")
        }
        definitions_by_id = {definition["id"]: definition for definition in definitions}

        values_by_local: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for value in values:
            definition = definitions_by_id.get(value.get("field_definition_id"))
            if not definition:
                continue
            display_value = None
            filter_value = None
            raw_value = None
            if definition["data_type"] == "text":
                raw_value = value.get("value_text")
                display_value = raw_value
                filter_value = raw_value
            elif definition["data_type"] == "number":
                raw_value = value.get("value_number")
                display_value = None if raw_value is None else str(raw_value)
                filter_value = raw_value
            elif definition["data_type"] == "date":
                raw_value = value.get("value_date")
                if hasattr(raw_value, "isoformat"):
                    raw_value = raw_value.isoformat()
                display_value = raw_value
                filter_value = raw_value
            elif definition["data_type"] == "select":
                option = options_by_id.get(value.get("selected_option_id"))
                raw_value = (option or {}).get("value")
                display_value = (option or {}).get("label") or raw_value
                filter_value = raw_value

            values_by_local.setdefault(value["local_id"], {})[definition["key"]] = {
                "field_definition_id": definition["id"],
                "display_value": display_value,
                "filter_value": filter_value,
                "raw_value": raw_value,
                "selected_option_id": value.get("selected_option_id"),
            }

        return LocalCustomFieldSnapshot(
            definitions=definitions,
            definitions_by_key=definitions_by_key,
            values_by_local=values_by_local,
        )

    def filter_local_ids_by_custom_filters(
        self,
        local_ids: Sequence[str],
        snapshot: LocalCustomFieldSnapshot,
        custom_filters: Optional[Dict[str, Any]],
    ) -> List[str]:
        if not custom_filters:
            return list(local_ids)

        def _match(expected: Any, actual: Any) -> bool:
            if isinstance(expected, list):
                return any(_match(item, actual) for item in expected)
            if actual is None:
                return expected in (None, "", EMPTY_GROUP_LABEL)
            return str(actual) == str(expected)

        matched = []
        for local_id in local_ids:
            local_values = snapshot.values_by_local.get(local_id, {})
            ok = True
            for key, expected in (custom_filters or {}).items():
                actual = (local_values.get(key) or {}).get("filter_value")
                if not _match(expected, actual):
                    ok = False
                    break
            if ok:
                matched.append(local_id)
        return matched

    def build_cube_response(
        self,
        sales_df: pd.DataFrame,
        grouping: str,
        metric: str,
        start_date: Optional[str],
        end_date: Optional[str],
        snapshot: LocalCustomFieldSnapshot,
        custom_dimension_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        if sales_df.empty:
            return {"columns": ["local_nombre", "TOTAL_FILA"], "data": [], "grand_totals": {}, "row_label": "Local"}

        if not custom_dimension_key:
            result = generate_sales_cube(
                sales_df,
                grouping,
                metric,
                start_date=start_date,
                end_date=end_date,
            )
            result["row_label"] = "Local"
            result["row_key"] = "local_nombre"
            result["hierarchical"] = False
            return result

        definition = snapshot.definitions_by_key.get(custom_dimension_key)
        if not definition:
            raise HTTPException(status_code=400, detail="La dimensión personalizada solicitada no existe en este mall.")

        df = sales_df.copy()
        df["local_id"] = df["local_id"].astype(str)
        df["fecha"] = pd.to_datetime(df["fecha"])
        grouping = (grouping or "DIA").upper()

        if grouping == "DIA":
            df["periodo"] = df["fecha"].dt.strftime("%d/%m")
        elif grouping == "SEMANA":
            df["periodo"] = "W" + df["fecha"].dt.isocalendar().week.astype(str)
        elif grouping == "MES":
            df["periodo"] = df["fecha"].dt.strftime("%Y-%m")

        def _dimension_for_local(local_id: str) -> str:
            local_values = snapshot.values_by_local.get(local_id, {})
            value = (local_values.get(custom_dimension_key) or {}).get("display_value")
            return value or EMPTY_GROUP_LABEL

        df["dimension_group"] = df["local_id"].map(_dimension_for_local)

        if metric == "transacciones" and "transacciones" in df.columns:
            metric_col = "transacciones"
            aggfunc = "sum"
        else:
            metric_col = metric if metric != "transacciones" else "id"
            aggfunc = "sum" if metric != "transacciones" else "count"
        if metric != "transacciones":
            df[metric_col] = pd.to_numeric(df[metric_col], errors="coerce").fillna(0)

        period_columns = self._build_period_columns(df, grouping, start_date, end_date)

        local_pivot = pd.pivot_table(
            df,
            values=metric_col,
            index=["dimension_group", "local_nombre"],
            columns="periodo",
            aggfunc=aggfunc,
            fill_value=0,
        ).reindex(columns=period_columns, fill_value=0)
        local_pivot["TOTAL_FILA"] = local_pivot.sum(axis=1)

        group_pivot = pd.pivot_table(
            df,
            values=metric_col,
            index="dimension_group",
            columns="periodo",
            aggfunc=aggfunc,
            fill_value=0,
        ).reindex(columns=period_columns, fill_value=0)
        group_pivot["TOTAL_FILA"] = group_pivot.sum(axis=1)

        data: List[Dict[str, Any]] = []
        for group_name in sorted(group_pivot.index, key=lambda value: (str(value) == EMPTY_GROUP_LABEL, str(value).lower())):
            group_row = {"row_label": str(group_name), "row_type": "group"}
            for column in list(period_columns) + ["TOTAL_FILA"]:
                group_row[column] = self._to_number(group_pivot.loc[group_name, column])
            data.append(group_row)

            group_locals = local_pivot.loc[group_name]
            if isinstance(group_locals, pd.Series):
                group_locals = group_locals.to_frame().T
                group_locals.index = [group_locals.index[0]]

            for local_name in sorted(group_locals.index.tolist(), key=lambda value: str(value).lower()):
                row = {"row_label": f"  {local_name}", "row_type": "local", "parent_label": str(group_name)}
                for column in list(period_columns) + ["TOTAL_FILA"]:
                    row[column] = self._to_number(group_locals.loc[local_name, column])
                data.append(row)

        grand_totals = {column: 0 for column in list(period_columns) + ["TOTAL_FILA"]}
        for column in period_columns:
            grand_totals[column] = self._to_number(group_pivot[column].sum())
        grand_totals["TOTAL_FILA"] = self._to_number(group_pivot["TOTAL_FILA"].sum())

        return {
            "columns": ["row_label", *period_columns, "TOTAL_FILA"],
            "data": data,
            "grand_totals": grand_totals,
            "row_label": definition["label"],
            "row_key": custom_dimension_key,
            "hierarchical": True,
        }

    def _build_period_columns(
        self,
        df: pd.DataFrame,
        grouping: str,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> List[str]:
        try:
            start_ts = pd.to_datetime(start_date) if start_date else df["fecha"].min().normalize()
            end_ts = pd.to_datetime(end_date) if end_date else df["fecha"].max().normalize()
            if grouping == "DIA":
                return pd.date_range(start=start_ts, end=end_ts, freq="D").strftime("%d/%m").tolist()
            if grouping == "SEMANA":
                values: List[str] = []
                seen = set()
                for current in pd.date_range(start=start_ts, end=end_ts, freq="D"):
                    label = f"W{int(current.isocalendar().week)}"
                    if label not in seen:
                        seen.add(label)
                        values.append(label)
                return values
            if grouping == "MES":
                return pd.period_range(start=start_ts, end=end_ts, freq="M").strftime("%Y-%m").tolist()
        except Exception:
            pass
        return sorted(df["periodo"].dropna().astype(str).unique().tolist())

    def _to_number(self, value: Any) -> Any:
        try:
            if isinstance(value, int):
                return int(value)
            if isinstance(value, float):
                return float(value)
            numeric = float(value)
            return int(numeric) if numeric.is_integer() else numeric
        except Exception:
            return value

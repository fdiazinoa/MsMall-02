import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

LOOKBACK_DAYS = 30
ALERT_WINDOW_DAYS = 7
RECENT_RUN_HOURS = 24
MIN_HISTORY_DAYS = 5
MIN_PATTERN_TRANSACTIONS = 8
ANALYSIS_PAGE_SIZE = 1000
MAX_ANALYSIS_PAGES = 12
TARGET_HISTORY_DAYS = 10
RUNS_TABLE = "ai_analysis_runs"
ALERTS_TABLE = "alertas_inteligentes"

RISK_PRIORITY = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}
RISK_SCORE_BY_LEVEL = {"ALTO": 80, "MEDIO": 45, "BAJO": 20}

ALERT_LABELS = {
    "BAJA_ANOMALA": "Caida abrupta",
    "FACTURA_PLANA": "Factura plana",
    "MONTO_REPETIDO_CONSECUTIVO": "Monto repetido consecutivo",
}

PERSISTED_ALERT_TYPE = {
    "BAJA_ANOMALA": "BAJA_ANOMALA",
    "FACTURA_PLANA": "COMPORTAMIENTO_ATIPICO",
    "MONTO_REPETIDO_CONSECUTIVO": "COMPORTAMIENTO_ATIPICO",
}

RULE_PREFIX_RE = re.compile(r"^\[(?P<rule>[A-Z_]+)\]\s*")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: Optional[datetime] = None) -> str:
    return (dt or _utcnow()).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    raw = str(value).strip()
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _normalize_date_value(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return pd.to_datetime(value, errors="coerce").date().isoformat()
    except Exception:
        return None


class AnalyticsService:
    def __init__(self, supabase_client: Optional[Client] = None, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("analytics-service")
        self.supabase: Client = supabase_client or self._build_client()

    def _build_client(self) -> Client:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError("Supabase credentials not found in environment")
        return create_client(SUPABASE_URL, SUPABASE_KEY)

    def _empty_snapshot(
        self,
        *,
        status: str,
        local_id: Optional[str],
        source: str,
        description: str,
        local_name: Optional[str] = None,
        run_at: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        evaluated_at = run_at or _iso_utc()
        return {
            "status": status,
            "source": source,
            "local_id": local_id,
            "local_nombre": local_name,
            "alerts": [],
            "summary": {
                "risk_state": "NO_DATA" if status != "ok" else "NORMAL",
                "risk_label": "Sin Datos" if status != "ok" else "Operacion Normal",
                "description": description,
                "last_evaluated_at": evaluated_at,
                "has_recent_run": status == "ok",
                "risk_score": 0,
                "alerts_count": 0,
                "analysis_window_days": LOOKBACK_DAYS,
                "detail": detail,
            },
        }

    def _fetch_store(self, local_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.supabase.table("locales")
                .select("id, nombre")
                .eq("id", local_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            return rows[0] if rows else None
        except Exception as exc:
            self.logger.warning("No se pudo cargar metadata del local %s: %s", local_id, exc)
            return None

    def _fetch_sales_rows(self, local_id: str, days: int = LOOKBACK_DAYS) -> List[Dict[str, Any]]:
        start_date = (date.today() - timedelta(days=max(days - 1, 0))).isoformat()
        target_days = min(days, TARGET_HISTORY_DAYS)
        collected: List[Dict[str, Any]] = []
        distinct_dates = set()

        for page in range(MAX_ANALYSIS_PAGES):
            start = page * ANALYSIS_PAGE_SIZE
            end = start + ANALYSIS_PAGE_SIZE - 1
            response = (
                self.supabase.table("ventas")
                .select("fecha, total_bruto, factura_no, hora_transaccion")
                .eq("local_id", local_id)
                .gte("fecha", start_date)
                .order("fecha", desc=True)
                .order("hora_transaccion", desc=True)
                .order("factura_no", desc=True)
                .range(start, end)
                .execute()
            )
            rows = response.data or []
            if not rows:
                break

            collected.extend(rows)
            distinct_dates.update(str(row.get("fecha")) for row in rows if row.get("fecha"))
            if len(distinct_dates) >= target_days and len(rows) < ANALYSIS_PAGE_SIZE:
                break
            if len(distinct_dates) >= target_days and page >= 1:
                break
            if len(rows) < ANALYSIS_PAGE_SIZE:
                break

        return collected

    def _to_sales_frame(self, rows: Sequence[Dict[str, Any]]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=["fecha", "total_bruto", "factura_no", "hora_transaccion"])

        df = pd.DataFrame(rows)
        if "fecha" not in df:
            df["fecha"] = None
        if "total_bruto" not in df:
            df["total_bruto"] = 0.0
        if "factura_no" not in df:
            df["factura_no"] = ""
        if "hora_transaccion" not in df:
            df["hora_transaccion"] = None

        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
        df["total_bruto"] = pd.to_numeric(df["total_bruto"], errors="coerce").fillna(0.0)
        df["factura_no"] = df["factura_no"].fillna("").astype(str).str.strip()
        df["hora_transaccion"] = df["hora_transaccion"].fillna("12:00:00").astype(str).str.strip()
        df["amount_2dp"] = df["total_bruto"].round(2)
        df = df[df["fecha"].notna()].copy()
        if df.empty:
            return df

        df["sort_hora"] = df["hora_transaccion"].replace({"": "12:00:00"}).fillna("12:00:00")
        df = df.sort_values(["fecha", "sort_hora", "factura_no", "amount_2dp"], kind="stable")
        return df

    def _build_alert(
        self,
        *,
        rule_code: str,
        risk_level: str,
        detected_on: Any,
        message: str,
        score: Optional[int] = None,
    ) -> Dict[str, Any]:
        fecha = _normalize_date_value(detected_on) or date.today().isoformat()
        return {
            "fecha": fecha,
            "tipo_alerta": PERSISTED_ALERT_TYPE.get(rule_code, "COMPORTAMIENTO_ATIPICO"),
            "rule_code": rule_code,
            "display_type": ALERT_LABELS.get(rule_code, rule_code.replace("_", " ").title()),
            "nivel_riesgo": risk_level,
            "mensaje": message,
            "score": score if score is not None else RISK_SCORE_BY_LEVEL.get(risk_level, 20),
        }

    def _detect_abrupt_sales_drop(self, daily_sales: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(daily_sales) < MIN_HISTORY_DAYS:
            return None

        ordered = daily_sales.sort_values("fecha", kind="stable").reset_index(drop=True)
        baseline = ordered.iloc[:-1]["total_bruto"].astype(float)
        current_row = ordered.iloc[-1]
        current_value = float(current_row["total_bruto"])
        baseline_mean = float(baseline.mean()) if not baseline.empty else 0.0
        baseline_std = float(baseline.std(ddof=0)) if len(baseline) > 1 else 0.0
        if baseline_mean <= 0:
            return None

        ratio = current_value / baseline_mean
        z_score = (current_value - baseline_mean) / baseline_std if baseline_std > 0 else 0.0
        drop_pct = max(0.0, (1 - ratio) * 100)

        if ratio <= 0.45 or (ratio <= 0.65 and z_score <= -1.5):
            level = "ALTO"
        elif ratio <= 0.75 and (baseline_std == 0.0 or z_score <= -1.0):
            level = "MEDIO"
        else:
            return None

        message = (
            f"Las ventas del dia cayeron {drop_pct:.1f}% frente al promedio reciente "
            f"(${baseline_mean:,.2f} vs ${current_value:,.2f})."
        )
        return self._build_alert(
            rule_code="BAJA_ANOMALA",
            risk_level=level,
            detected_on=current_row["fecha"],
            message=message,
        )

    def _detect_consecutive_amounts(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < MIN_PATTERN_TRANSACTIONS:
            return None

        max_streak = 1
        current_streak = 1
        max_amount = None
        streak_end_date = None
        amounts = df["amount_2dp"].tolist()
        dates = df["fecha"].tolist()

        for idx in range(1, len(amounts)):
            if amounts[idx] == amounts[idx - 1]:
                current_streak += 1
            else:
                current_streak = 1

            if current_streak > max_streak:
                max_streak = current_streak
                max_amount = amounts[idx]
                streak_end_date = dates[idx]

        if max_streak >= 8:
            level = "ALTO"
        elif max_streak >= 5:
            level = "MEDIO"
        else:
            return None

        message = (
            f"Se detectaron {max_streak} facturas consecutivas por ${float(max_amount):,.2f}. "
            "Conviene revisar si hubo duplicidad o patron manual."
        )
        return self._build_alert(
            rule_code="MONTO_REPETIDO_CONSECUTIVO",
            risk_level=level,
            detected_on=streak_end_date,
            message=message,
        )

    def _detect_flat_amounts(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        if len(df) < 12:
            return None

        amounts = df["amount_2dp"]
        counts = amounts.value_counts()
        if counts.empty:
            return None

        most_common_amount = float(counts.index[0])
        repeated_count = int(counts.iloc[0])
        repeated_share = repeated_count / max(len(df), 1)
        round_numbers = amounts.apply(lambda value: float(value).is_integer()).sum()
        round_share = round_numbers / max(len(df), 1)

        if repeated_count >= 25 and repeated_share >= 0.15:
            level = "ALTO"
        elif repeated_count >= 15 and repeated_share >= 0.08:
            level = "MEDIO"
        elif round_share >= 0.80 and repeated_share >= 0.04:
            level = "MEDIO"
        else:
            return None

        message = (
            f"El monto ${most_common_amount:,.2f} aparece {repeated_count} veces "
            f"({repeated_share:.0%} de la muestra reciente)."
        )
        if round_share >= 0.70:
            message += f" Ademas, {round_share:.0%} de las facturas terminan en monto redondo."

        return self._build_alert(
            rule_code="FACTURA_PLANA",
            risk_level=level,
            detected_on=df.iloc[-1]["fecha"],
            message=message,
        )

    def _summarize_snapshot(
        self,
        *,
        local_id: str,
        local_name: Optional[str],
        alerts: List[Dict[str, Any]],
        source: str,
        run_at: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        evaluated_at = run_at or _iso_utc()
        sorted_alerts = sorted(
            alerts,
            key=lambda item: (
                RISK_PRIORITY.get(item.get("nivel_riesgo"), 0),
                item.get("score", 0),
                item.get("fecha") or "",
            ),
            reverse=True,
        )
        risk_score = min(100, sum(_safe_int(item.get("score"), 0) for item in sorted_alerts))
        has_high = any(item.get("nivel_riesgo") == "ALTO" for item in sorted_alerts)
        has_medium = any(item.get("nivel_riesgo") == "MEDIO" for item in sorted_alerts)

        if has_high:
            risk_state = "HIGH"
            risk_label = "Riesgo Alto"
            description = "Se detectaron patrones con probabilidad alta de anomalia o manipulacion."
        elif has_medium:
            risk_state = "MEDIUM"
            risk_label = "Riesgo Medio"
            description = "Hay patrones atipicos que conviene revisar antes del cierre."
        else:
            risk_state = "NORMAL"
            risk_label = "Operacion Normal"
            description = "La ultima evaluacion no encontro patrones antifraude relevantes en la ventana analizada."

        if detail:
            description = detail

        return {
            "status": "ok",
            "source": source,
            "local_id": local_id,
            "local_nombre": local_name,
            "alerts": sorted_alerts,
            "summary": {
                "risk_state": risk_state,
                "risk_label": risk_label,
                "description": description,
                "last_evaluated_at": evaluated_at,
                "has_recent_run": True,
                "risk_score": risk_score,
                "alerts_count": len(sorted_alerts),
                "analysis_window_days": LOOKBACK_DAYS,
            },
        }

    def analyze_local(self, local_id: str, days: int = LOOKBACK_DAYS, recent_days: int = ALERT_WINDOW_DAYS) -> Dict[str, Any]:
        store = self._fetch_store(local_id)
        local_name = (store or {}).get("nombre")
        rows = self._fetch_sales_rows(local_id, days=days)
        sales_df = self._to_sales_frame(rows)
        evaluated_at = _iso_utc()
        if sales_df.empty:
            return self._empty_snapshot(
                status="no_data",
                local_id=local_id,
                local_name=local_name,
                source="live",
                run_at=evaluated_at,
                description="Este local aun no tiene ventas suficientes para evaluar riesgo.",
            )

        recent_cutoff = date.today() - timedelta(days=max(recent_days - 1, 0))
        recent_df = sales_df[sales_df["fecha"] >= recent_cutoff].copy()
        daily_sales = (
            sales_df.groupby("fecha", dropna=True)["total_bruto"]
            .sum()
            .reset_index()
            .sort_values("fecha", kind="stable")
        )

        alerts: List[Dict[str, Any]] = []
        abrupt_drop = self._detect_abrupt_sales_drop(daily_sales)
        if abrupt_drop:
            alerts.append(abrupt_drop)

        repeated_amounts = self._detect_consecutive_amounts(recent_df)
        if repeated_amounts:
            alerts.append(repeated_amounts)

        flat_amounts = self._detect_flat_amounts(recent_df)
        if flat_amounts:
            alerts.append(flat_amounts)

        enough_history = len(daily_sales) >= MIN_HISTORY_DAYS
        enough_pattern_window = len(recent_df) >= MIN_PATTERN_TRANSACTIONS
        if not alerts and not enough_history and not enough_pattern_window:
            return self._empty_snapshot(
                status="no_data",
                local_id=local_id,
                local_name=local_name,
                source="live",
                run_at=evaluated_at,
                description="No hay suficiente historico para validar tendencias antifraude con confianza.",
                detail=f"Solo hay {len(sales_df)} transacciones recientes disponibles.",
            )

        return self._summarize_snapshot(
            local_id=local_id,
            local_name=local_name,
            alerts=alerts,
            source="live",
            run_at=evaluated_at,
        )

    def _load_recent_run(self, local_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = (
                self.supabase.table(RUNS_TABLE)
                .select("*")
                .eq("local_id", local_id)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = response.data or []
            return rows[0] if rows else None
        except Exception as exc:
            self.logger.info("Tabla %s no disponible o inaccesible: %s", RUNS_TABLE, exc)
            return None

    def _load_recent_alerts(self, local_id: str) -> List[Dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=max(ALERT_WINDOW_DAYS - 1, 0))).isoformat()
        try:
            response = (
                self.supabase.table(ALERTS_TABLE)
                .select("*")
                .eq("local_id", local_id)
                .gte("fecha_detectada", cutoff)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            return response.data or []
        except Exception as exc:
            self.logger.info("Tabla %s no disponible o inaccesible: %s", ALERTS_TABLE, exc)
            return []

    def _format_stored_alert(self, row: Dict[str, Any]) -> Dict[str, Any]:
        raw_message = _clean_text(row.get("mensaje"))
        match = RULE_PREFIX_RE.match(raw_message)
        if match:
            rule_code = match.group("rule")
            message = raw_message[match.end():].strip()
        else:
            rule_code = "BAJA_ANOMALA" if row.get("tipo_alerta") == "BAJA_ANOMALA" else "FACTURA_PLANA"
            message = raw_message

        return {
            "id": row.get("id"),
            "fecha": _normalize_date_value(row.get("fecha_detectada")),
            "tipo_alerta": row.get("tipo_alerta"),
            "rule_code": rule_code,
            "display_type": ALERT_LABELS.get(rule_code, _clean_text(row.get("tipo_alerta")).replace("_", " ").title()),
            "nivel_riesgo": row.get("nivel_riesgo") or "MEDIO",
            "mensaje": message,
            "score": RISK_SCORE_BY_LEVEL.get(row.get("nivel_riesgo"), 20),
        }

    def _run_is_recent(self, run: Dict[str, Any]) -> bool:
        run_at = _coerce_iso_datetime(run.get("run_at"))
        if not run_at:
            return False
        return (_utcnow() - run_at) <= timedelta(hours=RECENT_RUN_HOURS)

    def _persist_run(self, local_id: str, snapshot: Dict[str, Any], trigger: str) -> bool:
        summary = snapshot.get("summary") or {}
        try:
            self.supabase.table(RUNS_TABLE).insert({
                "local_id": local_id,
                "status": snapshot.get("status") or "ok",
                "risk_state": summary.get("risk_state") or "NO_DATA",
                "risk_score": summary.get("risk_score") or 0,
                "alerts_count": summary.get("alerts_count") or 0,
                "run_at": summary.get("last_evaluated_at") or _iso_utc(),
                "trigger_source": trigger,
                "detail": summary.get("description"),
            }).execute()
            return True
        except Exception as exc:
            self.logger.info("No se pudo persistir corrida IA para %s: %s", local_id, exc)
            return False

    def _replace_alerts(self, local_id: str, alerts: Sequence[Dict[str, Any]]) -> bool:
        cutoff = (date.today() - timedelta(days=max(ALERT_WINDOW_DAYS - 1, 0))).isoformat()
        try:
            self.supabase.table(ALERTS_TABLE).delete().eq("local_id", local_id).gte("fecha_detectada", cutoff).execute()
            payload = []
            for alert in alerts:
                stored_rule = alert.get("rule_code") or "FACTURA_PLANA"
                payload.append({
                    "local_id": local_id,
                    "fecha_detectada": alert.get("fecha"),
                    "tipo_alerta": alert.get("tipo_alerta"),
                    "nivel_riesgo": alert.get("nivel_riesgo"),
                    "mensaje": f"[{stored_rule}] {alert.get('mensaje')}",
                })
            if payload:
                self.supabase.table(ALERTS_TABLE).insert(payload).execute()
            return True
        except Exception as exc:
            self.logger.info("No se pudieron persistir alertas IA para %s: %s", local_id, exc)
            return False

    def run_and_persist_local_analysis(self, local_id: str, trigger: str = "manual") -> Dict[str, Any]:
        snapshot = self.analyze_local(local_id)
        self._persist_run(local_id, snapshot, trigger)
        self._replace_alerts(local_id, snapshot.get("alerts") or [])
        return snapshot

    def get_alert_snapshot(self, local_id: str, allow_live_refresh: bool = True) -> Dict[str, Any]:
        store = self._fetch_store(local_id)
        local_name = (store or {}).get("nombre")
        recent_run = self._load_recent_run(local_id)
        if recent_run and self._run_is_recent(recent_run):
            if recent_run.get("status") and recent_run.get("status") != "ok":
                return self._empty_snapshot(
                    status=recent_run.get("status") or "no_data",
                    local_id=local_id,
                    local_name=local_name,
                    source="stored",
                    run_at=recent_run.get("run_at"),
                    description=recent_run.get("detail") or "Todavia no hay una corrida valida del semaforo para este local.",
                )
            stored_alerts = [self._format_stored_alert(row) for row in self._load_recent_alerts(local_id)]
            return self._summarize_snapshot(
                local_id=local_id,
                local_name=local_name,
                alerts=stored_alerts,
                source="stored",
                run_at=recent_run.get("run_at"),
                detail=recent_run.get("detail"),
            )

        if not allow_live_refresh:
            return self._empty_snapshot(
                status="no_data",
                local_id=local_id,
                local_name=local_name,
                source="none",
                description="Todavia no hay una corrida reciente del semaforo para este local.",
            )

        return self.run_and_persist_local_analysis(local_id, trigger="live_snapshot")

    def run_nightly_job(self) -> List[Dict[str, Any]]:
        stores_resp = self.supabase.table("locales").select("id").execute()
        results = []
        for store in stores_resp.data or []:
            local_id = store.get("id")
            if not local_id:
                continue
            try:
                results.append(self.run_and_persist_local_analysis(local_id, trigger="nightly"))
            except Exception as exc:
                self.logger.error("Fallo analizando local %s en corrida nocturna: %s", local_id, exc)
        return results


def run_local_risk_analysis(
    local_id: str,
    *,
    supabase_client: Optional[Client] = None,
    logger: Optional[logging.Logger] = None,
    trigger: str = "manual",
) -> Dict[str, Any]:
    service = AnalyticsService(supabase_client=supabase_client, logger=logger)
    return service.run_and_persist_local_analysis(local_id, trigger=trigger)


if __name__ == "__main__":
    service = AnalyticsService()
    service.run_nightly_job()

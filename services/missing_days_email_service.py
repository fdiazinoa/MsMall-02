"""HTML templates for missing-days email notifications."""

from html import escape
from typing import Any, Dict, List, Optional


def _status_color(missing_count: int) -> Dict[str, str]:
    if missing_count > 5:
        return {
            "label": "Critico",
            "border": "#fecdd3",
            "background": "#fff1f2",
            "text": "#9f1239",
            "icon_bg": "#ffe4e6",
        }
    return {
        "label": "Alerta",
        "border": "#facc15",
        "background": "#fffbeb",
        "text": "#92400e",
        "icon_bg": "#fef3c7",
    }


def build_missing_days_email_html(
    *,
    mall_name: str,
    local_name: str,
    fecha_inicio: str,
    fecha_fin: str,
    missing_details: List[Dict[str, Any]],
    report_url: Optional[str] = None,
) -> str:
    """Builds the HTML body used for missing-sales-days alerts."""
    missing_count = len(missing_details)
    palette = _status_color(missing_count)
    safe_mall = escape(mall_name or "Mall")
    safe_local = escape(local_name or "Local")
    safe_start = escape(fecha_inicio)
    safe_end = escape(fecha_fin)
    safe_report_url = escape(report_url or "")

    cards = []
    for item in missing_details:
        date = escape(str(item.get("fecha") or item.get("fecha_faltante") or ""))
        cause = escape(str(item.get("causa") or "Sin transacciones registradas"))
        log_id = item.get("log_id")
        log_line = ""
        if log_id:
            log_line = (
                '<div style="margin-top:6px;color:#94a3b8;font-size:11px;line-height:1.35;">'
                f"Log ID: #{escape(str(log_id))}"
                "</div>"
            )

        cards.append(
            f"""
            <td style="padding:0 12px 12px 0;width:50%;vertical-align:top;">
              <div style="border:1px solid #fde68a;border-radius:8px;background:#ffffff;padding:14px 16px;">
                <div style="display:flex;gap:10px;align-items:flex-start;">
                  <div style="color:#94a3b8;font-size:18px;line-height:1;">&#9888;</div>
                  <div>
                    <div style="font-size:16px;font-weight:700;color:#334155;line-height:1.25;">{date}</div>
                    <div style="margin-top:4px;color:#64748b;font-size:12px;font-weight:700;line-height:1.35;">{cause}</div>
                    {log_line}
                  </div>
                </div>
              </div>
            </td>
            """
        )

    rows = []
    for idx in range(0, len(cards), 2):
        rows.append(f"<tr>{''.join(cards[idx:idx + 2])}</tr>")

    report_button = ""
    if safe_report_url:
        report_button = f"""
          <div style="padding:20px 24px 0;text-align:right;">
            <a href="{safe_report_url}" style="display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:8px;padding:10px 16px;font-size:13px;font-weight:700;">
              Ver auditoria en MSMALL
            </a>
          </div>
        """

    if missing_count == 0:
        return f"""
        <!doctype html>
        <html>
          <body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
            <div style="max-width:760px;margin:0 auto;padding:24px;">
              <div style="border:1px solid #bbf7d0;border-radius:14px;background:#f0fdf4;padding:22px;">
                <div style="font-size:18px;font-weight:800;color:#166534;">Auditoria completa</div>
                <div style="margin-top:8px;font-size:14px;color:#166534;">
                  {safe_local} no tiene dias faltantes entre {safe_start} y {safe_end}.
                </div>
              </div>
            </div>
          </body>
        </html>
        """

    return f"""
    <!doctype html>
    <html>
      <body style="margin:0;background:#f8fafc;font-family:Arial,Helvetica,sans-serif;color:#1e293b;">
        <div style="display:none;max-height:0;overflow:hidden;">
          Faltan ventas para {missing_count} dias en {safe_local}.
        </div>
        <div style="max-width:820px;margin:0 auto;padding:24px;">
          <div style="margin-bottom:14px;color:#64748b;font-size:13px;">
            {safe_mall} &middot; {safe_local} &middot; Periodo {safe_start} al {safe_end}
          </div>

          <div style="border:1px solid {palette['border']};border-radius:14px;background:{palette['background']};overflow:hidden;">
            <div style="padding:22px 24px;border-bottom:1px solid {palette['border']};">
              <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                <tr>
                  <td style="width:42px;vertical-align:top;">
                    <div style="width:36px;height:36px;border-radius:999px;background:{palette['icon_bg']};color:#f59e0b;text-align:center;line-height:36px;font-size:18px;">&#9888;</div>
                  </td>
                  <td style="vertical-align:top;">
                    <div style="font-size:20px;line-height:1.3;font-weight:800;color:#7c2d12;">
                      Atencion: Faltan ventas para {missing_count} dias
                    </div>
                    <div style="margin-top:6px;font-size:14px;line-height:1.45;color:#9a3412;">
                      Se detectaron dias sin transacciones registradas en el periodo seleccionado.
                    </div>
                  </td>
                  <td style="text-align:right;vertical-align:top;">
                    <span style="display:inline-block;border:1px solid {palette['border']};border-radius:999px;padding:6px 10px;font-size:12px;font-weight:800;color:{palette['text']};background:#ffffff;">
                      {palette['label']}
                    </span>
                  </td>
                </tr>
              </table>
            </div>

            <div style="padding:16px 18px 22px;">
              <div style="color:#f59e0b;text-transform:uppercase;font-size:12px;letter-spacing:.04em;font-weight:800;margin:0 0 14px 0;">
                Detalle de dias faltantes y auditoria de logs
              </div>
              <table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                {''.join(rows)}
              </table>
            </div>
          </div>

          {report_button}

          <div style="padding:18px 4px 0;color:#94a3b8;font-size:11px;line-height:1.45;">
            Este mensaje fue generado automaticamente por MSMALL. Revise la causa antes de contactar al local o reintentar la carga.
          </div>
        </div>
      </body>
    </html>
    """

"""
Servicio de exportación de reportes
Contiene toda la lógica de generación de archivos Excel y PDF
"""

import io
from typing import Optional, List, Dict, Any
from datetime import datetime
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from supabase import Client
from services.local_custom_fields_service import LocalCustomFieldsService

class ExportService:
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.local_custom_fields_service = LocalCustomFieldsService(supabase_client, logger=None)
    
    # --- UTILS ---
    def _get_header_style(self):
        return PatternFill(start_color="1F4788", end_color="1F4788", fill_type="solid"), Font(bold=True, color="FFFFFF", size=11)
    
    def _format_currency(self, value):
        if value is None: return "$0.00"
        return f"${value:,.2f}"

    def _get_pdf_styles(self):
        styles = getSampleStyleSheet()
        title = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=18, textColor=colors.HexColor('#1F4788'), spaceAfter=12, alignment=TA_CENTER, fontName='Helvetica-Bold')
        subtitle = ParagraphStyle('CustomSubtitle', parent=styles['Normal'], fontSize=12, textColor=colors.grey, spaceAfter=20, alignment=TA_CENTER)
        header = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#1F4788'), spaceBefore=12, spaceAfter=6, fontName='Helvetica-Bold')
        return title, subtitle, header, styles['Normal']

    # --- SALES REPORT ---

    async def generate_sales_report_excel(self, fecha_inicio: str, fecha_fin: str, local_id: Optional[str] = None, report_type: str = 'detailed') -> io.BytesIO:
        # 1. Fetch Data
        query = self.supabase.table('ventas').select('local_id, locales(nombre), fecha, hora, factura_no, total_neto, total_impuestos, total_bruto').gte('fecha', fecha_inicio).lte('fecha', fecha_fin)
        if local_id:
            query = query.eq('local_id', local_id)
        response = query.execute()
        data = response.data
        if not data:
            data = []

        df = pd.DataFrame(data)
        # Flatten locales(nombre)
        if not df.empty:
            df['nombre_local'] = df['locales'].apply(lambda x: x.get('nombre') if x else 'Desc')
        else:
            df = pd.DataFrame(columns=['local_id', 'nombre_local', 'total_neto', 'total_impuestos', 'total_bruto', 'fecha', 'hora', 'factura_no'])

        wb = Workbook()
        ws = wb.active
        ws.title = "Reporte de Ventas"
        
        ws['A1'] = 'REPORTE DE AUDITORÍA DE VENTAS'
        ws['A2'] = f'Período: {fecha_inicio} al {fecha_fin} ({report_type.capitalize()})'
        ws['A1'].font = Font(size=14, bold=True)
        
        fill, font = self._get_header_style()
        
        if report_type == 'detailed':
            # --- VISTA DETALLADA (Filas Individuales) ---
            headers = ['Local', 'Fecha', 'Hora', 'Factura #', 'Bruto', 'Impuestos', 'Neto']
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=4, column=col, value=h)
                cell.fill = fill
                cell.font = font
                ws.column_dimensions[chr(64+col)].width = 15
            
            if not df.empty:
                # Ordenar: Nombre Local, Fecha, Hora
                df_sorted = df.sort_values(by=['nombre_local', 'fecha', 'hora'])
                
                row_idx = 5
                for _, row in df_sorted.iterrows():
                    ws.cell(row=row_idx, column=1, value=row.get('nombre_local'))
                    ws.cell(row=row_idx, column=2, value=row.get('fecha'))
                    ws.cell(row=row_idx, column=3, value=row.get('hora'))
                    ws.cell(row=row_idx, column=4, value=row.get('factura_no'))
                    ws.cell(row=row_idx, column=5, value=row.get('total_neto')).number_format = '$#,##0.00;[Red]-$#,##0.00'  # Bruto UI
                    ws.cell(row=row_idx, column=6, value=row.get('total_impuestos')).number_format = '$#,##0.00;[Red]-$#,##0.00'
                    ws.cell(row=row_idx, column=7, value=row.get('total_bruto')).number_format = '$#,##0.00;[Red]-$#,##0.00' # Neto UI
                    row_idx += 1
        
        else:
            # --- VISTA RESUMIDA (Agrupada) ---
            headers = ['Local', 'Ventas Brutas (Base)', 'Impuestos', 'Ventas Netas (Total)']
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=4, column=col, value=h)
                cell.fill = fill
                cell.font = font
                cell.alignment = Alignment(horizontal="center")
                ws.column_dimensions[chr(64+col)].width = 20

            if not df.empty:
                resumen = df.groupby(['local_id', 'nombre_local']).agg({
                    'total_neto': 'sum',
                    'total_impuestos': 'sum',
                    'total_bruto': 'sum'
                }).reset_index()
                
                row_idx = 5
                for _, row in resumen.iterrows():
                    ws.cell(row=row_idx, column=1, value=row['nombre_local'])
                    ws.cell(row=row_idx, column=2, value=row['total_neto']).number_format = '$#,##0.00;[Red]-$#,##0.00'
                    ws.cell(row=row_idx, column=3, value=row['total_impuestos']).number_format = '$#,##0.00;[Red]-$#,##0.00'
                    ws.cell(row=row_idx, column=4, value=row['total_bruto']).number_format = '$#,##0.00;[Red]-$#,##0.00'
                    row_idx += 1
                
                # Totales
                ws.cell(row=row_idx, column=1, value='TOTAL').font = Font(bold=True)
                ws.cell(row=row_idx, column=2, value=resumen['total_neto'].sum()).number_format = '$#,##0.00;[Red]-$#,##0.00'
                ws.cell(row=row_idx, column=2).font = Font(bold=True)
                ws.cell(row=row_idx, column=3, value=resumen['total_impuestos'].sum()).number_format = '$#,##0.00;[Red]-$#,##0.00'
                ws.cell(row=row_idx, column=3).font = Font(bold=True)
                ws.cell(row=row_idx, column=4, value=resumen['total_bruto'].sum()).number_format = '$#,##0.00;[Red]-$#,##0.00'
                ws.cell(row=row_idx, column=4).font = Font(bold=True)

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    async def generate_sales_report_pdf(self, fecha_inicio: str, fecha_fin: str, local_id: Optional[str] = None, report_type: str = 'detailed', mall_name: str = "CENTRO COMERCIAL MS MALL") -> io.BytesIO:
        # Fetch Data (Reuse logic? For now duplicate for speed)
        query = self.supabase.table('ventas').select('local_id, locales(nombre), fecha, total_neto, total_impuestos, total_bruto').gte('fecha', fecha_inicio).lte('fecha', fecha_fin)
        if local_id: query = query.eq('local_id', local_id)
        data = query.execute().data
        df = pd.DataFrame(data or [])
        if not df.empty:
            df['nombre_local'] = df['locales'].apply(lambda x: x.get('nombre') if x else '?')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        title_style, subtitle_style, header_style, normal_style = self._get_pdf_styles()
        
        elements.append(Paragraph(f"CENTRO COMERCIAL {mall_name.upper()}", title_style))
        elements.append(Paragraph("REPORTE DE AUDITORÍA DE VENTAS", title_style))
        elements.append(Paragraph(f"Período: {fecha_inicio} - {fecha_fin}", subtitle_style))
        elements.append(Spacer(1, 12))

        # Resumen
        elements.append(Paragraph("RESUMEN EJECUTIVO", header_style))
        
        total_base = df['total_neto'].sum() if not df.empty else 0
        total_tax = df['total_impuestos'].sum() if not df.empty else 0
        total_final = df['total_bruto'].sum() if not df.empty else 0
        tx_count = len(df)
        
        summary_data = [
            ["Total Ventas Brutas (Base):", self._format_currency(total_base)],
            ["Total Impuestos:", self._format_currency(total_tax)],
            ["Total Ventas Netas:", self._format_currency(total_final)],
            ["Transacciones:", str(tx_count)]
        ]
        t_summary = Table(summary_data, colWidths=[200, 150])
        t_summary.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 24))
        
        # Tabla Detalle (ONLY IF DETAILED)
        if report_type == 'detailed' and not df.empty:
            elements.append(Paragraph("DETALLE POR LOCAL", header_style))
            resumen = df.groupby(['local_id', 'nombre_local']).agg({'total_neto':'sum', 'total_impuestos':'sum', 'total_bruto':'sum'}).reset_index()
            
            table_data = [['Local', 'Ventas Brutas', 'Impuestos', 'Ventas Netas']]
            for _, row in resumen.iterrows():
                table_data.append([
                    row['nombre_local'],
                    self._format_currency(row['total_neto']),
                    self._format_currency(row['total_impuestos']),
                    self._format_currency(row['total_bruto'])
                ])
            # Footer
            table_data.append(['TOTAL', self._format_currency(total_base), self._format_currency(total_tax), self._format_currency(total_final)])
            
            t = Table(table_data, colWidths=[150, 100, 100, 100])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F4788')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('GRID', (0,0), (-1,-1), 1, colors.grey),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#C5D9F1')),
                ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
            ]))
            elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        return buffer

    # --- SALES CUBE ---

    async def generate_sales_cube_excel(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        agrupacion: str,
        metrica: str,
        mall_id: str = None,
        local_id: str = None,
        custom_dimension_key: Optional[str] = None,
        custom_filters: Optional[Dict[str, Any]] = None
    ) -> io.BytesIO:
        # Same logic as get_sales_cube in main.py but exporting
        stores_query = self.supabase.table("locales").select("id, nombre")
        if mall_id:
            stores_query = stores_query.eq("mall_id", mall_id)
        if local_id:
            stores_query = stores_query.eq("id", local_id)
        stores = stores_query.execute().data
        store_map = {str(s['id']): s['nombre'] for s in stores}
        local_ids = list(store_map.keys())
        snapshot = self.local_custom_fields_service.build_snapshot(mall_id, local_ids, include_inactive=False) if mall_id else self.local_custom_fields_service.build_snapshot("", [], include_inactive=False)
        if custom_filters:
            local_ids = self.local_custom_fields_service.filter_local_ids_by_custom_filters(local_ids, snapshot, custom_filters)

        sales = []
        if local_ids:
            page_size = 1000
            page = 0
            while True:
                sales_query = self.supabase.table("ventas").select("*").gte("fecha", fecha_inicio).lte("fecha", fecha_fin)
                if local_id:
                    sales_query = sales_query.eq("local_id", local_id)
                else:
                    sales_query = sales_query.in_("local_id", local_ids)
                res = sales_query.order("fecha").range(page * page_size, (page + 1) * page_size - 1).execute()
                chunk = res.data or []
                if not chunk:
                    break
                sales.extend(chunk)
                if len(chunk) < page_size:
                    break
                page += 1
        
        wb = Workbook()
        ws = wb.active
        ws.title = "Matriz de Ventas"
        
        ws['A1'] = "MATRIZ DE VENTAS"
        ws['A2'] = f"Agrupación: {agrupacion} | Métrica: {metrica}"
        ws['A1'].font = Font(size=14, bold=True)
        
        if not sales:
            ws['A4'] = "No data found"
        else:
            df = pd.DataFrame(sales)
            df['local_id'] = df['local_id'].astype(str)
            df['local_nombre'] = df['local_id'].map(store_map).fillna(df['local_id'])
            cube = self.local_custom_fields_service.build_cube_response(
                df,
                grouping=agrupacion.upper(),
                metric=metrica,
                start_date=fecha_inicio,
                end_date=fecha_fin,
                snapshot=snapshot,
                custom_dimension_key=custom_dimension_key,
            )
            
            # Write Headers
            ws.cell(row=4, column=1, value=cube.get("row_label") or "Local")
            fill, font = self._get_header_style()
            ws.cell(row=4, column=1).fill = fill
            ws.cell(row=4, column=1).font = font
            
            visible_columns = [col for col in cube["columns"] if col != "row_label"]
            col_idx = 2
            for col_name in visible_columns:
                c = ws.cell(row=4, column=col_idx, value=col_name)
                c.fill = fill
                c.font = font
                col_idx += 1
            
            # Write Data
            row_idx = 5
            for row in cube["data"]:
                label = row.get("row_label") or row.get("local_nombre") or ""
                ws.cell(row=row_idx, column=1, value=str(label))
                if row.get("row_type") == "group":
                    ws.cell(row=row_idx, column=1).font = Font(bold=True)
                c_idx = 2
                for col_name in visible_columns:
                    val = row.get(col_name, 0)
                    ws.cell(row=row_idx, column=c_idx, value=val).number_format = '$#,##0.00' if metrica != 'transacciones' else '0'
                    if row.get("row_type") == "group":
                        ws.cell(row=row_idx, column=c_idx).font = Font(bold=True)
                    c_idx += 1
                row_idx += 1
            
            # Total Row
            ws.cell(row=row_idx, column=1, value="TOTAL").font = Font(bold=True)
            c_idx = 2
            for col_name in visible_columns:
                col_sum = cube["grand_totals"].get(col_name, 0)
                ws.cell(row=row_idx, column=c_idx, value=col_sum).number_format = '$#,##0.00' if metrica != 'transacciones' else '0'
                ws.cell(row=row_idx, column=c_idx).font = Font(bold=True)
                c_idx += 1

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    # --- FINANCIAL DASHBOARD ---

    async def _get_financial_data(self, fecha_inicio, fecha_fin):
        # Logic from getKPIs to calculate OCR
        sales = self.supabase.table("ventas").select("local_id, total_bruto, total_neto").gte("fecha", fecha_inicio).lte("fecha", fecha_fin).execute().data
        stores = self.supabase.table("locales").select("*").execute().data
        store_map = {str(s['id']): s for s in stores}
        
        agg = {}
        for s in sales:
            lid = str(s['local_id'])
            if lid not in agg: agg[lid] = {'neto':0, 'bruto':0}
            agg[lid]['neto'] += (s['total_neto'] or 0)
            agg[lid]['bruto'] += (s['total_bruto'] or 0) # This is Total
        
        results = []
        for lid, store in store_map.items():
            vals = agg.get(lid, {'neto':0, 'bruto':0})
            venta_neta_total = vals['bruto'] # USER TERM: Netas = Total
            # Previous logic in frontend used 'venta' = salesMap value.
            # Usually salesMap in frontend was populated by sum of bruto? Check main.py dashboard logic.
            # main.py dashboard logic: sales_by_store[s_name] += bruto.
            # And frontend calls it "Venta Actual".
            # So "Venta Netas" (User Term) = Bruto (DB).
            
            renta_fija = float(store.get('renta_fija') or 0)
            mts = float(store.get('mts') or 1)
            breakpoint = float(store.get('breakpoint_venta') or 0)
            pct = float(store.get('porcentaje_variable') or store.get('porciento_renta') or 0)
            
            ocr = (renta_fija / venta_neta_total * 100) if venta_neta_total > 0 else 0
            
            renta_var = 0
            if venta_neta_total > breakpoint:
                renta_var = (venta_neta_total * pct / 100) - renta_fija
                if renta_var < 0: renta_var = 0
            
            status = "Saludable"
            if ocr > 20: status = "Riesgo"
            elif ocr > 15: status = "Atención"
            
            results.append({
                "nombre": store['nombre'],
                "ventas": venta_neta_total,
                "renta_fija": renta_fija,
                "breakpoint": breakpoint,
                "renta_var": renta_var,
                "ocr": ocr,
                "venta_m2": venta_neta_total / mts,
                "estado": status
            })
        return results

    async def generate_financial_dashboard_excel(self, fecha_inicio: str, fecha_fin: str) -> io.BytesIO:
        data = await self._get_financial_data(fecha_inicio, fecha_fin)
        wb = Workbook()
        ws = wb.active
        ws.title = "Salud de Cartera"
        
        ws['A1'] = "SALUD DE CARTERA - ANÁLISIS FINANCIERO"
        ws['A2'] = f"Período: {fecha_inicio} al {fecha_fin}"
        ws['A1'].font = Font(size=14, bold=True)
        
        headers = ['Local', 'Ventas Netas', 'Renta Fija', 'Break-point', 'Renta Variable', 'OCR (%)', 'Venta/m2', 'Estado']
        fill, font = self._get_header_style()
        for col, h in enumerate(headers, 1):
            c = ws.cell(row=4, column=col, value=h)
            c.fill = fill
            c.font = font
            ws.column_dimensions[chr(64+col)].width = 15
            
        row_idx = 5
        for item in data:
            ws.cell(row=row_idx, column=1, value=item['nombre'])
            ws.cell(row=row_idx, column=2, value=item['ventas']).number_format = '$#,##0.00'
            ws.cell(row=row_idx, column=3, value=item['renta_fija']).number_format = '$#,##0.00'
            ws.cell(row=row_idx, column=4, value=item['breakpoint']).number_format = '$#,##0.00'
            ws.cell(row=row_idx, column=5, value=item['renta_var']).number_format = '$#,##0.00'
            ws.cell(row=row_idx, column=6, value=item['ocr']/100).number_format = '0.00%'
            ws.cell(row=row_idx, column=7, value=item['venta_m2']).number_format = '$#,##0.00'
            ws.cell(row=row_idx, column=8, value=item['estado'])
            
            if item['ocr'] > 20:
                ws.cell(row=row_idx, column=8).fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
            row_idx += 1

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    async def generate_financial_dashboard_pdf(self, fecha_inicio: str, fecha_fin: str) -> io.BytesIO:
        data = await self._get_financial_data(fecha_inicio, fecha_fin)
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        title_s, sub_s, head_s, norm_s = self._get_pdf_styles()
        
        elements.append(Paragraph("SALUD DE CARTERA", title_s))
        elements.append(Paragraph(f"{fecha_inicio} - {fecha_fin}", sub_s))
        
        table_data = [['Local', 'Ventas Netas', 'Renta Fija', 'Var', 'OCR %', 'Estado']]
        for d in data:
            table_data.append([
                d['nombre'],
                self._format_currency(d['ventas']),
                self._format_currency(d['renta_fija']),
                self._format_currency(d['renta_var']),
                f"{d['ocr']:.2f}%",
                d['estado']
            ])
            
        t = Table(table_data)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F4788')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 1, colors.grey),
        ]))
        elements.append(t)
        
        doc.build(elements)
        buffer.seek(0)
        return buffer

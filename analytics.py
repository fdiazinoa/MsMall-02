import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Optional

def calcular_kpis_inmobiliarios(ventas_df, locales_df):
    """
    Calcula Ventas por m2 y Tasa de Esfuerzo (OCR).
    OCR = (Renta Fija / Venta Total) * 100
    """
    if ventas_df.empty or locales_df.empty:
        return pd.DataFrame()

    # Agrupar ventas por local
    resumen_ventas = ventas_df.groupby('local_id')['total_bruto'].sum().reset_index()
    
    # Merge con locales
    df = pd.merge(resumen_ventas, locales_df, left_on='local_id', right_on='id')
    
    # Asegurar tipos numéricos
    df['total_bruto'] = pd.to_numeric(df['total_bruto'], errors='coerce').fillna(0)
    df['mts'] = pd.to_numeric(df['mts'], errors='coerce').replace(0, 1).fillna(1)
    df['renta_fija'] = pd.to_numeric(df['renta_fija'], errors='coerce').fillna(0)
    
    # Cálculos
    df['ventas_m2'] = df['total_bruto'] / df['mts']
    df['ocr'] = np.where(df['total_bruto'] > 0, (df['renta_fija'] / df['total_bruto']) * 100, 0)
    
    return df

def proyeccion_cierre_mes(ventas_df):
    """
    Proyecta el cierre de ventas del mes actual ponderando fines de semana.
    """
    if ventas_df.empty:
        return 0
    
    df = ventas_df.copy()
    df['fecha'] = pd.to_datetime(df['fecha'])
    
    # Obtener info del mes
    hoy = datetime.now()
    dias_transcurridos = hoy.day
    _, ultimo_dia = pd.Timestamp(hoy.year, hoy.month, 1).days_in_month, hoy.replace(day=1).replace(month=hoy.month % 12 + 1, day=1) - timedelta(days=1)
    # Simplified days calculation
    last_day = pd.Period(hoy.strftime('%Y-%m'), freq='M').end_time.day
    dias_restantes = last_day - dias_transcurridos
    
    # Factor de ponderación: Sábado(5) y Domingo(6) pesan 20% más
    df['is_weekend'] = df['fecha'].dt.dayofweek.isin([5, 6])
    df['weight'] = np.where(df['is_weekend'], 1.2, 1.0)
    
    total_ponderado = (df['total_bruto'] * df['weight']).sum()
    promedio_ponderado_diario = total_ponderado / df['weight'].sum() if df['weight'].sum() > 0 else 0
    
    venta_actual = df['total_bruto'].sum()
    proyeccion = venta_actual + (promedio_ponderado_diario * dias_restantes)
    
    return round(proyeccion, 2)

def detectar_breakpoint(venta_proyectada, renta_fija, breakpoint_venta, porcentaje_variable):
    """
    Calcula si el local paga renta variable basado en el breakpoint.
    """
    if venta_proyectada > breakpoint_venta:
        # Paga el % de la venta total o solo del excedente? 
        # Comúnmente en Retail es el MAYOR entre Fija vs % Venta.
        renta_variable_calculada = venta_proyectada * (porcentaje_variable / 100)
        excedente = max(0, renta_variable_calculada - renta_fija)
        return excedente
    return 0

def generate_sales_cube(
    ventas_df: pd.DataFrame,
    grouping: str = 'DIA',
    metric: str = 'total_neto',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """
    Genera una matriz de ventas (Cubo) pivotando los datos.
    
    Args:
        ventas_df: DataFrame con los datos de ventas.
        grouping: 'DIA', 'SEMANA', 'MES'.
        metric: 'total_neto', 'total_bruto', 'transacciones' (count).
        
    Returns:
        Dict con estructura de matriz: columns, data (rows), grand_totals.
    """
    if ventas_df.empty:
        return {"columns": [], "data": [], "grand_totals": {}}

    df = ventas_df.copy()
    
    # Asegurar tipo fecha
    df['fecha'] = pd.to_datetime(df['fecha'])
    
    grouping = (grouping or 'DIA').upper()

    # Crear columna dinámica para columnas de la matriz
    if grouping == 'DIA':
        df['periodo'] = df['fecha'].dt.strftime('%d/%m')
    elif grouping == 'SEMANA':
        df['periodo'] = 'W' + df['fecha'].dt.isocalendar().week.astype(str)
    elif grouping == 'MES':
        df['periodo'] = df['fecha'].dt.strftime('%Y-%m')
    
    # Pivot Table
    # Rows: local_nombre (asumimos que viene en el DF, si no, usar local_id)
    # Columna pivote: 'periodo'
    # Valor: metric
    agg = 'sum' if metric != 'transacciones' else 'count'
    
    # Si la metrica es transacciones, usamos cualquier columna para contar, ej: id
    value_col = metric if metric != 'transacciones' else 'id'
    
    pivot = pd.pivot_table(
        df, 
        values=value_col, 
        index='local_nombre', 
        columns='periodo', 
        aggfunc=agg, 
        fill_value=0
    )

    # Build full period range so matrix includes days/weeks/months with zero sales.
    try:
        start_ts = pd.to_datetime(start_date) if start_date else df['fecha'].min().normalize()
        end_ts = pd.to_datetime(end_date) if end_date else df['fecha'].max().normalize()

        if pd.isna(start_ts) or pd.isna(end_ts):
            full_periods = list(pivot.columns)
        elif grouping == 'DIA':
            full_periods = pd.date_range(start=start_ts, end=end_ts, freq='D').strftime('%d/%m').tolist()
        elif grouping == 'SEMANA':
            # Keep same label format ("W<week>") as existing UI.
            full_periods = []
            seen = set()
            for d in pd.date_range(start=start_ts, end=end_ts, freq='D'):
                label = f"W{int(d.isocalendar().week)}"
                if label not in seen:
                    seen.add(label)
                    full_periods.append(label)
        elif grouping == 'MES':
            full_periods = pd.period_range(start=start_ts, end=end_ts, freq='M').strftime('%Y-%m').tolist()
        else:
            full_periods = list(pivot.columns)

        if full_periods:
            pivot = pivot.reindex(columns=full_periods, fill_value=0)
    except Exception:
        # Non-critical: if range generation fails, keep default pivot columns.
        pass
    
    # Calcular Totales por Fila
    pivot['TOTAL_FILA'] = pivot.sum(axis=1)
    
    # Calcular Totales por Columna (Grand Totals)
    grand_totals = pivot.sum(axis=0).to_dict()
    
    # Formatear Salida
    # Reset index para que 'local_nombre' sea una columna más
    pivot = pivot.reset_index()
    
    # Convertir a lista de dicts
    data = pivot.to_dict(orient='records')
    
    # Columnas ordenadas (Local, fechas..., TOTAL)
    cols = ['local_nombre'] + [c for c in pivot.columns if c not in ['local_nombre', 'TOTAL_FILA']] + ['TOTAL_FILA']
    
    return {
        "columns": cols,
        "data": data,
        "grand_totals": grand_totals
    }

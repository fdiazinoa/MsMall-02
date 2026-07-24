# MsMall Big Data - Sprint 1

## Resultado

El Sprint 1 añade analítica comercial incremental sobre las ventas existentes. Mantiene intactos los importadores, dashboards, tablas y políticas Legacy; los nuevos endpoints leen únicamente agregados.

```mermaid
flowchart LR
  I[FTP/SFTP/Exportador/API existentes] --> V[ventas Legacy]
  V --> Q[Trigger: cola por mall y fecha]
  Q --> W[worker_importacion.py]
  W --> A[refresh_big_data_aggregates]
  A --> D[Agregados diarios y mensuales]
  A --> M[Watermark y runs]
  D --> E[/api/v1/big-data]
  F[mall_feature_flags: BIG_DATA_CORE] --> E
  E --> U[Panel Big Data]
```

## Despliegue

1. Ejecutar `20260724_big_data_sprint_1.sql` en Supabase, fuera de horas pico si el volumen de ventas es alto.
2. Desplegar backend y worker con la misma versión. El worker procesa la cola; no se ejecutan cálculos en solicitudes HTTP.
3. Activar sólo el mall contratado:

```sql
INSERT INTO public.mall_feature_flags (mall_id, feature_key, enabled)
VALUES ('<mall-uuid>', 'BIG_DATA_CORE', true)
ON CONFLICT (mall_id, feature_key) DO UPDATE SET enabled = true, updated_at = now();
```

4. Encolar la primera reconstrucción por el endpoint `POST /api/v1/big-data/rebuild` como administrador/IT, o insertar fechas en `big_data_refresh_queue`.
5. Esperar un ciclo del worker y comprobar `big_data_refresh_runs`, `big_data_watermarks` y el panel **Big Data**.

## Validación de paridad

Para cada mall de volumen alto, medio y pequeño, comparar el mismo rango:

```sql
SELECT coalesce(sum(total_neto), 0) AS legacy_neto, count(*) AS legacy_transacciones
FROM public.ventas WHERE mall_id = '<mall-uuid>' AND fecha BETWEEN '<inicio>' AND '<fin>';

SELECT coalesce(sum(sales_net), 0) AS agregado_neto, coalesce(sum(transaction_count), 0) AS agregado_transacciones
FROM public.big_data_daily_aggregates
WHERE mall_id = '<mall-uuid>' AND grain = 'mall' AND period_date BETWEEN '<inicio>' AND '<fin>';
```

Las diferencias deben ser cero. Si no lo son, no habilitar el flag y revisar `big_data_refresh_runs` antes de reencolar el rango.

## Rollback

El rollback operativo no toca ventas ni locales:

```sql
UPDATE public.mall_feature_flags
SET enabled = false, updated_at = now()
WHERE mall_id = '<mall-uuid>' AND feature_key = 'BIG_DATA_CORE';
```

El panel y endpoints quedarán bloqueados para ese mall. Los importadores y reportes Legacy continúan funcionando. La eliminación de tablas nuevas o del trigger sólo debe realizarse en una migración posterior revisada; no es necesaria para desactivar el módulo.

## Riesgos pendientes

- La primera reconstrucción se debe medir con datos reales y comparar paridad antes de activar comercialmente.
- La clasificación comercial es progresiva: los locales sin homologar quedan como rubro Legacy o `Sin clasificar`.
- La cola agrupa por mall y fechas; para reconstrucciones muy extensas, encolar tramos acotados.

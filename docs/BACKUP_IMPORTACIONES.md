# Backup de importaciones

La sección **Backup de importaciones** permite descargar un CSV de ventas almacenadas
del Mall activo. Usa el permiso existente `sales_reports.view`, tanto en el menú de
escritorio y móvil como en las dos rutas del backend.

## Uso

1. Seleccionar el Mall desde la cabecera.
2. Elegir fecha inicial y final por **fecha de venta**, ambas incluidas.
3. Elegir todos los locales o seleccionar uno o varios por nombre/código.
4. Pulsar **Descargar CSV**. El resultado informa cuántos registros se descargaron.

Se incluyen locales inactivos. Cambiar de Mall restablece el formulario y cancela las
peticiones anteriores. Un período sin ventas devuelve un CSV con los encabezados.

## Columnas

| Columna | Fuente |
| --- | --- |
| `id_registro` | `ventas.id` |
| `mall_id`, `mall_nombre` | Mall autorizado de los locales |
| `local_id`, `codigo_local`, `local_nombre` | Identidad del local en `locales` |
| `fecha_venta` | `ventas.fecha` |
| `hora_transaccion` | `ventas.hora_transaccion`, o `ventas.hora` cuando la primera no está disponible |
| `numero_transaccion` | `ventas.factura_no` |
| `tipo_registro` | `metadata.granularity`: `transaction` → `transaccion`; `daily`/`daily_summary` → `resumen_diario` |
| `total_bruto`, `total_impuestos`, `total_neto` | Valores almacenados, sin recalcular ni intercambiar importes |
| `fecha_creacion_registro` | `ventas.created_at`; conserva la zona horaria almacenada |
| `fecha_importacion` | `metadata.fecha_importacion`, o `logs_carga.fecha_hora` con lote y local coincidentes |
| `canal_importacion` | `metadata.canal_importacion`, canal del log coincidente, o `WebService` para el origen explícito `exporter_webservice` |
| `archivo_origen` | `metadata.archivo_origen`, o archivo del log coincidente |
| `batch_id` | `ventas.metadata.batch_id` |

Son 18 columnas, una fila por venta/resumen almacenado. La trazabilidad solo enlaza
logs exitosos o parciales del mismo Mall, local y lote, usando el último log completado.
No se deduce el origen a partir de fechas cercanas ni de la configuración actual del local.
Los valores desconocidos quedan vacíos; los ceros reales se conservan. Las fechas de
creación e importación son campos distintos.

El archivo utiliza UTF-8 con BOM y escape CSV estándar para comas, comillas y saltos
de línea. Los textos que podrían ejecutarse como fórmulas en una hoja de cálculo se
prefijan con apóstrofo; los importes negativos permanecen numéricos.

## API y generación

- `GET /api/v1/export/import-backup/stores`: catálogo mínimo de locales del Mall.
- `POST /api/v1/export/import-backup/csv`: genera y entrega el archivo.
- Ambas rutas requieren `Authorization: Bearer …` y contexto `X-Mall-Id` autorizado.

```json
{
  "fecha_inicio": "2026-01-01",
  "fecha_fin": "2026-01-31",
  "local_ids": null
}
```

`local_ids: null` incluye todos los locales. Para una selección, enviar una lista de
UUID; una lista vacía o con locales ajenos se rechaza. El rango invertido devuelve 400;
fechas o UUID inválidos devuelven 422. No hay un límite artificial de filas.

Las consultas se paginan por `(fecha, id)` y dividen los identificadores de locales
en grupos de 100. La pertenencia se obtiene de `locales.mall_id`, incluyendo ventas
históricas cuyo `mall_id` desnormalizado no esté poblado. No se consultan credenciales
de las conexiones de los locales.

El backend termina el archivo antes de responder para evitar entregar un CSV parcial
si falla una consulta. Mantiene hasta 8 MiB en memoria y luego utiliza disco temporal;
el archivo se cierra al finalizar la respuesta. La descarga del navegador usa un Blob.
La respuesta incluye `Cache-Control: no-store`, `Content-Length` y `X-Backup-Records`.

La generación registra usuario, Mall, período, locales y cantidad de filas en
`system_audit_logs`, con acción `backup_importaciones_generado`. Si falla esa auditoría,
se registra una advertencia en el servidor y se conserva la descarga.

La exportación lee el estado disponible durante su generación; no abre una instantánea
transaccional entre las consultas. No conserva archivos originales ni versiones previas
de ventas corregidas. No agrega migraciones ni modifica el importador o el POS local.

## Validación

```sh
python3 -m pytest tests/test_import_backup.py tests/test_sales_query_service.py tests/test_audit_summary_api.py tests/test_role_permissions_rbac.py tests/test_cors_production.py -q
node --test tests/import_backup_api.test.cjs
npm run build
```

# Liberación de huellas diferenciales — 26 de noviembre de 2026

Solicitud: liberar el almacenamiento auxiliar de respaldos diferenciales sin borrar ventas ni afectar los archivos existentes.

## Operación ejecutada en producción

- Proyecto Supabase: MsMall (`tqvdlceyuvngfftqobjv`).
- API y ftp-import-worker de Railway: `ENABLE_DIFFERENTIAL_BACKUPS=false` y `ENABLE_SCHEDULED_SQL_BACKUPS=false`. Ambos despliegues finalizaron en SUCCESS antes de la purga.
- Se verificó que la tabla no tenía triggers de usuario ni referencias entrantes que requirieran CASCADE.
- Se ejecutó únicamente `TRUNCATE TABLE msmall_backup.row_fingerprints`, dentro de una transacción con lock_timeout de 5 s y statement_timeout de 30 s.
- Se conservaron `msmall_backup.baselines`, el catálogo `sql_artifacts`, los archivos de Storage y todas las tablas operativas.

## Evidencia antes/después

| Medida | Antes | Después |
|---|---:|---:|
| Base de datos (bytes) | 6.568.291.475 | 4.639.329.427 |
| Tabla de huellas e índices (bytes) | 1.928.978.432 | 16.384 |
| Filas de ventas | 4.238.731 | 4.238.731 |
| Bases auxiliares | 2 | 2 |
| Entradas del catálogo de archivos | 8 | 8 |
| Fragmentos en sql-backups | 32 | 32 |

La huella MD5 del catálogo de objetos (IDs, nombres y metadatos ordenados) se mantuvo en `e0d0e51c20293b50ef2c2d42b8561d0a`. No es un checksum del contenido de los ZIP: prueba que el catálogo observado no cambió. No se realizaron operaciones de escritura en Storage.

Los cuatro archivos completados (dos completos y dos diferenciales) tenían todos sus fragmentos y la suma de tamaños esperada. Cada diferencial tenía su completo original correspondiente.

## Restauración y límites

La generación usa `msmall_backup.row_fingerprints` en el origen. Los archivos ya generados se restauran usando el SQL del completo original y un diferencial; su control de base vive en `msmall_restore.baselines` del destino, no en las huellas del origen.

La prueba de integración añadida genera archivos con datos sintéticos, elimina las huellas del origen y restaura completo+diferencial en otra base PostgreSQL local. Verifica los datos restaurados y que las ventas del origen no se borraron. No se restauraron los archivos reales de producción.

La automatización SQL y su limpieza periódica quedan detenidas. No se modificaron los vencimientos existentes de los archivos; el endpoint de descarga mantiene sus controles de expiración. Los backups SQL por período y la ingesta FTP/SFTP no se deshabilitaron.

No reactivar la generación diferencial con las antiguas huellas vacías. Para reintroducir esa función se necesita un nuevo completo base que reconstruya las huellas, y asumir su consumo de disco, o implementar otro almacenamiento auxiliar. Los registros pequeños de baselines se conservaron como metadatos de los archivos existentes; no representan una base utilizable para nuevos diferenciales tras la purga.

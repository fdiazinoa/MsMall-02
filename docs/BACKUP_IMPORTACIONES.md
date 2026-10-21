# Backup de importaciones

La sección **Backup de importaciones** permite descargar un CSV de ventas almacenadas
del Mall activo. Usa el permiso existente `sales_reports.view`, tanto en el menú de
escritorio y móvil como en las dos rutas del backend.

## Uso

1. Seleccionar el Mall desde la cabecera.
2. Elegir fecha inicial y final por **fecha de venta**, ambas incluidas.
3. Elegir todos los locales o seleccionar uno o varios por nombre/código.
4. Pulsar **Descargar CSV**. El resultado informa cuántos registros se descargaron.

La tarjeta **Tu cuota disponible** muestra solicitudes restantes, volumen personal,
volumen compartido del Mall, descargas en curso y tiempo de espera. Se actualiza al
terminar una solicitud, al recuperar el foco y cada 30 segundos mientras la página
esté visible. También permite actualización manual.

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
fechas o UUID inválidos devuelven 422. No se truncan filas: si el archivo excede su
presupuesto se rechaza completo con 413 y se indica reducir el período o los locales.

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
de ventas corregidas. La migración de cuotas agrega tablas propias; no modifica las
ventas, el importador ni el POS local.

## Límites y configuración

| Control | Valor inicial |
| --- | --- |
| Simultáneas por usuario | 1, compartida entre sus Malls |
| Simultáneas por Mall | 2, entre todos sus usuarios |
| Intervalo entre solicitudes del usuario | 60 segundos, incluso cambiando de Mall |
| Solicitudes diarias del usuario | 10 |
| Tamaño máximo del CSV | 50 MB |
| Volumen diario del usuario | 200 MB, entre todos sus Malls |
| Volumen diario del Mall | 1.000 MB |
| Período máximo por solicitud | 90 días inclusivos |

Se usan MB decimales: 1 MB = 1.000.000 bytes. El día de cuota se renueva a medianoche
en `America/Santo_Domingo`, usando la hora de Postgres. El tamaño contabilizado es el
del CSV generado, no una estimación de la factura de tráfico de los proveedores.

Los administradores pueden editar los ocho valores en **Configurar límites globales**.
Se guardan en `import_backup_policy` y se aplican a todos los usuarios y Malls,
conservando el consumo acumulado del día. Las reservas ya admitidas conservan su
presupuesto; los valores nuevos gobiernan las solicitudes siguientes.

La configuración requiere un administrador validado en el perfil/rol asignado por el
servidor o la cuenta administradora del sistema. Las pistas de rol de `user_metadata`
no conceden configuración global ni acceso a backups de Malls ajenos.

Rutas adicionales:

- `GET /api/v1/export/import-backup/quota`: cuota del usuario autenticado y Mall activo.
- `PUT /api/v1/export/import-backup/settings`: reemplazo de los ocho límites globales;
  requiere administrador. Los campos omitidos toman los valores iniciales del modelo.

El consumo se coordina mediante `import_backup_quota_control`, una función
`SECURITY INVOKER` ejecutable solo por `service_role`. Sus tres tablas tienen RLS y
no conceden acceso directo a `anon` ni `authenticated`. No se envían claves de servicio
al navegador. Un bloqueo transaccional corto protege las operaciones de contabilidad
entre instancias; no abarca las lecturas de ventas, la generación o la transferencia.

Antes de generar, se reserva el menor valor entre el máximo por archivo y los saldos
disponibles del usuario y del Mall. Al terminar de generar se cobran los bytes reales
y se libera la diferencia. La plaza de concurrencia se retiene durante la transmisión.
Las solicitudes admitidas que fallan o se cancelan siguen consumiendo un intento y
el intervalo de espera; los fallos de generación cobran los bytes ya escritos. Las
peticiones rechazadas antes de reservar no consumen una solicitud diaria.

Una reserva se renueva cada 20 segundos y vence tras dos minutos sin renovación. Si
se pierde el proceso generador, se libera su plaza y se cobra conservadoramente el
presupuesto reservado cuyo consumo se desconoce. Si ya estaba transmitiendo, no se
cobra dos veces. Las desconexiones normales liberan la reserva al cerrar la respuesta.
Los trabajos que atraviesan medianoche se liquidan contra el día en que se admitieron.

Se devuelve 429 con `Retry-After` para frecuencia, concurrencia y cuota diaria; 400
para exceso de días y 413 para exceso de tamaño. Si no se puede verificar la cuota,
la descarga se bloquea con 503; no existe una alternativa sin límites.

## Despliegue

Aplicar primero `supabase/migrations/20261020235502_import_backup_quotas.sql`, después
desplegar el backend y finalmente el frontend. La migración fue validada en Postgres
local aislado; este PR no aplica cambios a la base de producción. Si falta la migración,
el backend nuevo devuelve 503 al intentar consultar cuotas o generar un backup.

## Validación

```sh
python3 -m pytest tests/test_import_backup.py tests/test_import_backup_quota_service.py tests/test_sales_query_service.py tests/test_audit_summary_api.py tests/test_role_permissions_rbac.py tests/test_cors_production.py -q
node --test tests/import_backup_api.test.cjs
npm run build
```

La suite de concurrencia usa Postgres real, sin Docker ni dependencias Python extra:

```sh
BACKUP_QUOTA_TEST_DSN=postgresql://postgres@127.0.0.1:55437/msmall_backup_quota_test \
  python3 -m pytest tests/test_import_backup_quotas_postgres.py -q
```

La base debe ser local y desechable, llamarse exactamente `msmall_backup_quota_test`,
tener los roles `anon`, `authenticated` y `service_role` (este último con BYPASSRLS),
y ejecutarse con un propietario con permisos DDL. La suite recrea `public` y `auth`
únicamente en esa base y rechaza otras direcciones/nombres. Sin la variable, esas
pruebas se omiten; las pruebas unitarias y HTTP restantes se ejecutan normalmente.


### Navegación y permisos

- **Herramientas → Backup de importaciones** requiere `import_backup.view`, independiente de `sales_reports.view`. El permiso **Ver** habilita consultar locales, cuota y descargar CSV; se configura en Usuarios y Roles.
- La migración `import_backup_role_permissions` copia el acceso de Reportes de ventas de cada rol existente, sin sobrescribir permisos de Backup ya definidos. Después se administra por separado.
- **Administración → Límites globales de backup** requiere `backup_settings.view` para consultar y `backup_settings.update` (junto con Ver) para guardar, configurables en Usuarios y Roles como **Configurar límites globales de backup**. Son independientes del permiso de descarga; GET/PUT `/api/v1/export/import-backup/settings` validan Ver/Editar en el servidor. El permiso Editar cambia los límites de todos los usuarios y Malls. La asignación no amplía el acceso a los datos de otros Malls.
- La cuota disponible sigue visible en Backup; su panel no contiene controles administrativos.

- La migración `import_backup_settings_permissions` habilita Ver/Editar inicialmente solo a Administrador y conserva las concesiones o revocaciones existentes. Los demás roles pueden recibir estos permisos explícitamente. Los administradores legados verificados conservan compatibilidad mientras se asigna su rol RBAC.

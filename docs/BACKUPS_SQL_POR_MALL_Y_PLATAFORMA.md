# Backups SQL por Mall

> La descarga completa de plataforma fue retirada de la aplicación. La API devuelve `platform: false` por compatibilidad con clientes anteriores y rechaza ese alcance con HTTP 404, incluso para el administrador global. Solo queda disponible el backup del Mall seleccionado. Las referencias al formato completo más abajo documentan el generador interno anterior, sin acceso desde la aplicación.

En **Backups → Backup**, la sección **Backup del Mall y de la plataforma** permite descargar un ZIP SQL independiente de los CSV existentes. No hay endpoint de restauración SQL y estos archivos no se aceptan en Restore desde CSV.

## Permisos

- Se requiere sesión válida y permiso de lectura de `import_backup`.
- **Por Mall:** administrador verificado y asignado al Mall seleccionado, o administrador global. La asignación se verifica en el servidor; un administrador local no obtiene acceso a otro Mall por cambiar `X-Mall-Id`.
- **Plataforma:** exclusivamente la identidad global cuyo correo autenticado coincide con `SYSTEM_ADMIN_EMAILS`, obtenido del servidor de Auth. Un rol llamado `admin`, `superadmin` o metadatos editables no habilitan esta opción.
- La API de capacidades devuelve solo permisos y disponibilidad, nunca credenciales ni la cadena de conexión. El frontend muestra botones según esa respuesta; el POST vuelve a comprobarlos.

## Contenido

| Alcance | Archivos |
| --- | --- |
| Mall seleccionado | `schema.sql` (estructura común de `public`, sin propietarios ni grants), `data.sql` (datos del Mall), `manifest.json` |
| Plataforma | `schema.sql` (esquemas no internos que exporte `pg_dump`), `data.sql`, `roles.sql` (sin contraseñas de roles), `manifest.json` |

**Mall:** incluye `malls.id`, `locales.mall_id`, tablas con `mall_id`, tablas con `local_id` verificado a través de los locales del Mall, y descendientes por claves foráneas simples de `public`. Una venta legacy sin `mall_id` se incluye por su local; si tiene un `mall_id` distinto al seleccionado, se excluye. Las tablas indirectas con varios padres clasificados deben pertenecer al mismo Mall por todos sus padres no nulos. Las tablas sin pertenencia demostrable se excluyen; el manifiesto lista las tablas incluidas y excluidas. Las claves compuestas no se usan para inferir pertenencia. Los ciclos de dependencias entre tablas fallan explícitamente y requieren revisión o backup completo.

El dump por Mall **no es una copia autónoma de todo el proyecto**: usuarios Auth, roles PostgreSQL, catálogos globales y otros datos compartidos no se incluyen. La recuperación requiere un esquema compatible y las dependencias globales existentes. `schema.sql` es estructura común, no debe ejecutarse sobre una aplicación operativa para recuperar un solo Mall. El SQL de datos se ordena por dependencias y usa COPY dentro de una transacción; no sobrescribe ni elimina datos existentes. Resolver conflictos o secuencias de identidades durante recuperación corresponde a un procedimiento administrativo en un entorno de prueba.

**Plataforma:** utiliza `pg_dump` para esquema y datos del mismo snapshot, y `pg_dumpall --roles-only --no-role-passwords` para roles. Conserva grants en el dump completo; no conserva propietarios mediante `--no-owner`. No contiene datos de `storage.buckets_vectors` ni `storage.vector_indexes`. Los roles son globales y se capturan por separado del snapshot de datos. No se presenta como copia física ni PITR.

Ningún alcance incluye archivos físicos de Storage, variables de entorno, claves configuradas fuera de tablas, código, Edge Functions ni infraestructura del proyecto. Para recuperar Supabase se deben revisar los roles y esquemas administrados según su procedimiento oficial; no ejecutar los SQL ciegamente en un proyecto existente.

**Datos sensibles:** estos SQL incluyen los valores almacenados, incluidas credenciales/configuraciones en tablas. No tienen el filtrado de secretos de los CSV. El ZIP se sirve con `Cache-Control: no-store`; guardarlo cifrado y con acceso restringido. No se persisten ZIP públicos ni se crean URLs compartidas.

## Configuración del servidor (deshabilitado por defecto)

Se requieren ambas variables, exclusivamente en el backend:

- `ENABLE_DATABASE_BACKUPS=true`
- `BACKUP_DATABASE_URL`: conexión PostgreSQL al **mismo proyecto/base de MsMall**. Usar conexión directa o pooler en modo sesión, no transaction pooler. Usar TLS (`sslmode=require` o validación más estricta). Verificar el destino antes de habilitar: la aplicación no puede deducir automáticamente la correspondencia entre una URL de Auth y el host de un pooler.

No configurar el DSN en variables `VITE_*`, frontend, repositorio ni peticiones del navegador. Las credenciales se pasan a libpq mediante entorno y nunca mediante argumentos de proceso o mensajes de error.

El Dockerfile incluye `postgresql-client` y requirements fija `psycopg[binary]==3.3.6`. `pg_dump`/`pg_dumpall` deben tener una versión compatible con el servidor: comprobarla durante el despliegue. Un cliente más antiguo que PostgreSQL puede rechazar el dump. El usuario PostgreSQL necesita lectura de las tablas y acceso suficiente para exportar roles. Si faltan permisos o falla una etapa, no se entrega un ZIP parcial.

No se ha configurado el DSN ni habilitado esta función en producción como parte de este cambio.

## Límites y operación

- Las consultas de datos se ejecutan en una transacción PostgreSQL `REPEATABLE READ, READ ONLY`; esquema y datos usan el mismo snapshot exportado.
- Generación limitada a diez minutos, conexión a diez segundos y espera de locks a diez segundos. Un error de PostgreSQL se devuelve sin DSN ni stderr sensible.
- Se reutilizan las reservas/cuotas existentes de Backups: usuario y Mall activo. Esto incluye el backup completo. La duración no depende del selector de fechas ni de la selección de locales del formulario CSV.
- El límite de tamaño se aplica al contenido temporal sin comprimir y al ZIP final. Un backup completo puede requerir aumentar los límites globales; si no cabe, se rechaza sin descarga parcial.
- La reserva se renueva durante la generación y se cierra al finalizar la descarga o ante error. Los archivos temporales y procesos se limpian al fallar. La solicitud de generación no se reintenta automáticamente.
- Mantener la pantalla abierta. Cancelar/cerrar el navegador no garantiza detener inmediatamente el trabajo ya iniciado en el backend; sigue sujeto a tiempo y cuota.
- Los proxies externos pueden tener límites de duración menores; para bases que excedan esos límites se requiere una estrategia de jobs/almacenamiento privado, fuera de este cambio.
- El log registra alcance, Mall de contabilidad, usuario y bytes; no registra el contenido SQL ni la conexión.

## Validación sin producción

La suite levanta un clúster PostgreSQL desechable **solo en socket UNIX local**, con dos Malls y tablas relacionadas. Genera ambos ZIP, comprueba exclusión del otro Mall, incluye ventas legacy y dependencias indirectas, excluye tablas globales del archivo por Mall, rechaza relaciones cruzadas y reproduce el SQL en tablas vacías con claves foráneas dentro de ese clúster. También prueba permisos, ausencia de secretos en errores, cuotas, formato de respuesta y opción deshabilitada.

No utiliza el DSN de producción para las pruebas. No se ejecutan backups ni restauraciones de producción. No se modifican esquema, permisos, POS ni los CSV actuales.

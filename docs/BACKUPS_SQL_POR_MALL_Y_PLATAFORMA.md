# Backups SQL por Mall

> La descarga completa de plataforma fue retirada de la aplicación. La API devuelve `platform: false` por compatibilidad con clientes anteriores y rechaza ese alcance con HTTP 404, incluso para el administrador global. Solo queda disponible el backup del Mall seleccionado. Las referencias al formato completo más abajo documentan el generador interno anterior, sin acceso desde la aplicación.

En **Backups → Backup SQL**, la sección **Backup del Mall y de la plataforma** permite descargar un ZIP SQL independiente de los CSV existentes. No hay endpoint de restauración SQL y estos archivos no se aceptan en Restore desde CSV.

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


## Pestaña Backup SQL y fechas

La descarga SQL del Mall se ubica en la pestaña **Backup SQL**, separada de los CSV. Requiere fecha inicial y final, inicialmente del mes actual; ambas fechas están incluidas. El período se envía al servidor y se aplica a `ventas.fecha` y `logs_carga.fecha_hora`, en zona `America/Santo_Domingo`. Los descendientes por FK siguen los padres incluidos en el período. Locales, configuraciones y otras tablas sin este filtro temporal conservan su alcance completo por Mall. Por tanto, el período no constituye un filtro global de cada timestamp de la base.

La reserva de cuota utiliza la duración real del período y respeta el máximo de días configurado. El ZIP incluye el período y la zona horaria en `manifest.json`. No utiliza el selector de fechas de los CSV.

Un `OperationalError` al abrir PostgreSQL no se corrige reduciendo fechas. La aplicación ahora clasifica fallos de autenticación, TLS, DNS y red en mensajes seguros; nunca muestra el mensaje original con host, usuario o contraseña. Revisar `BACKUP_DATABASE_URL` en Railway según el diagnóstico, manteniendo el modo Session pooler. La mera presencia de la variable y los binarios habilita los botones; no garantiza que la contraseña/conexión sea válida.

## Opción diferencial por Mall

Deshabilitada por defecto. Requiere las migraciones `database_backup_differential` y
`database_backup_file_ceiling`, además de `ENABLE_DIFFERENTIAL_BACKUPS=true` en el
backend y los requisitos habituales de `ENABLE_DATABASE_BACKUPS`. El usuario de
`BACKUP_DATABASE_URL` necesita leer los datos y administrar las dos tablas privadas
de `msmall_backup`; las claves REST no conceden este acceso. No conceder ese esquema
a `anon`, `authenticated` o `service_role` ni añadirlo a los esquemas expuestos.

La pestaña ofrece tres modos cuando está habilitada:

- **SQL por período:** conserva el comportamiento existente; no sirve como base.
- **Completo para base diferencial:** captura todo el alcance del Mall sin fechas,
  genera `schema.sql`, `data.sql` y `manifest.json` y registra claves primarias y
  huellas SHA-256 de las filas exportadas. Solo escribe estos metadatos privados;
  no modifica tablas operativas ni instala triggers. Una generación exitosa
  reemplaza la única base vigente de ese Mall. Si falla antes de terminar el ZIP,
  la transacción revierte y conserva la base anterior.
- **Diferencial:** usa el ID de la base vigente y el mismo alcance, compara el estado
  actual completo de las filas con las huellas y exporta altas, modificaciones y
  eliminaciones acumuladas desde esa base. Incluye correcciones de ventas antiguas,
  cambios de claves y filas que salieron del alcance por cambios de pertenencia.
  No usa `fecha`, `created_at` ni `updated_at` para detectar cambios. No avanza la
  base: cada diferencial se compara siempre con el completo original.

El completo y las huellas comparten un snapshot PostgreSQL `REPEATABLE READ`.
Cada diferencial utiliza otro snapshot coherente y solo lee. Un advisory lock
exclusivo por Mall evita generar/reemplazar bases y diferenciales simultáneamente,
sin bloquear las escrituras ordinarias de importación. Los locks de lectura del
catálogo sí pueden bloquear DDL; hay timeout. Las tablas del alcance necesitan una
clave primaria exportable. Se admiten claves primarias y foráneas compuestas;
se rechazan ciclos que no se pueden ordenar con seguridad. Para relaciones
compuestas se comparan todas las parejas de columnas al validar pertenencia y se
ordenan los padres antes de los hijos. Una FK con columnas nulas no demuestra
pertenencia para una tabla sin raíz Mall/local propia. Esto amplía el alcance de
completos base y diferenciales a descendientes por claves compuestas; el SQL por
período conserva su comportamiento anterior. Se mantienen las exclusiones de Auth,
Storage físico y catálogos globales.

La huella del esquema normaliza los tokens aleatorios de `pg_dump` y compara la
estructura de `public` antes de exportar. Si el esquema cambia, falta la base, fue
reemplazada o corresponde a otro Mall, se exige crear un completo nuevo. Cambiar la
versión de `pg_dump` también puede requerir una base nueva. El alcance compuesto
usa una nueva versión de huella: cualquier base anterior requiere regenerarse.
No hay migración
automática de esquemas durante una recuperación diferencial.

### Recuperación y conservación

Conservar el ZIP completo original y el diferencial deseado. El sistema almacena
**huellas**, no una copia recuperable del completo: si se pierde el ZIP base, hay
que generar otro completo. La referencia en pantalla acredita generación, no que
el usuario haya conservado su descarga. Incluso si se interrumpe una descarga
después de generar el ZIP, la nueva referencia puede haber reemplazado la anterior.
Los respaldos ya descargados siguen siendo utilizables con su base original.

Procedimiento administrativo, solo en una base de recuperación compatible y
aislada:

1. Preparar esquema y dependencias compartidas (Auth, catálogos y otros requisitos
   no incluidos). `schema.sql` es estructura común: no ejecutarlo en producción.
   Un dump de esquema puede contener `CREATE SCHEMA public`; preparar el destino
   vacío de acuerdo con ese SQL y sus dependencias, sin eliminar esquemas operativos.
2. Restaurar `data.sql` del completo con `psql -X -v ON_ERROR_STOP=1`. Se registra
   el ID base en `msmall_restore.baselines` dentro de la misma transacción.
3. Restaurar `data.sql` de **un** diferencial de esa base. El SQL verifica y bloquea
   su marcador, carga tablas temporales, elimina hijos antes de padres y aplica
   inserciones/actualizaciones en orden de dependencias. Incluye columnas identity
   con `OVERRIDING SYSTEM VALUE` y omite las columnas calculadas.
4. Validar los datos, permisos, triggers y secuencias antes de poner el destino en
   servicio. Como en el backup por Mall existente, las dependencias globales y los
   valores de secuencias no se reconstruyen automáticamente.

Nunca encadenar diferenciales. Para recuperar otro punto, preparar de nuevo el
completo original y aplicar únicamente el diferencial elegido. El marcador cambia
al finalizar y rechaza reejecuciones, bases equivocadas o aplicar un diferencial
sobre otro. No detecta ediciones manuales hechas al destino después del completo;
el destino debe permanecer reservado a la recuperación. No hay endpoint que
ejecute estos SQL ni se restaura sobre producción desde la aplicación.

### Cuotas, costo y límites de esta entrega

Todos los modos usan los permisos, reservas, cuotas diarias, timeout de diez minutos
y controles de tamaño existentes. Los modos base/diferencial no admiten fechas;
reservan una solicitud, no un período de ventas. El máximo administrativo admitido
por archivo pasa de 1.000 a **5.000 MB**, sin elevar el valor configurado (50 MB por
defecto), la cuota diaria ni la cantidad de solicitudes. Para generar bases grandes
hay que configurar explícitamente una cuota suficiente. Esta entrega no implementa
planes comerciales, cuotas mensuales ni programación automática de diferenciales.

Las huellas consumen espacio en PostgreSQL proporcional al número de filas de la
base; al reemplazar una base se eliminan lógicamente las huellas anteriores (el
espacio físico se recupera según el mantenimiento de PostgreSQL). La comparación
recorre datos del Mall y calcula hashes en el servidor. Reduce la transferencia de
filas sin cambios, pero no elimina el costo de CPU, lecturas ni generación de
esquema. No se promete un tamaño diferencial fijo.

Validación local con PostgreSQL desechable: completo + diferencial se reproducen
en otra base con FKs reales, claves compuestas, columnas identity/calculadas,
correcciones con fechas antiguas, altas, eliminaciones y preservación del otro
Mall. Se prueban límites, cancelación, rollback de metadatos, cambio de esquema,
bases ausentes/obsoletas, permisos y flag apagado. No se han medido el tiempo,
disco temporal, memoria del navegador (la descarga usa Blob) ni restauración de
los respaldos multi-GB de Agora/Santiago. Validar esa capacidad antes de habilitar
la opción o comprometer una oferta comercial. No se aplican estas migraciones ni
se activa la opción en producción como parte de la creación del PR.

## Plan SQL gratuito compartido y programación diaria

La ampliación opcional agrupa Malls en una bolsa privada de tráfico, independiente
de los CSV y sus cuotas anteriores. Para Ágora y Santiago Center se configura una
bolsa conjunta de **40.000.000.000 bytes semanales** (40 GB decimales), con máximo
de **5.000.000.000 bytes por archivo**, precio cero y sin mecanismo de sobrecargo.
La semana comienza los lunes a las 00:00 de `America/Santo_Domingo`, sin acumulación.
Cuando no hay presupuesto suficiente, se bloquea la generación o descarga.

Las tablas `msmall_backup.traffic_*` y la función `traffic_control` son privadas,
con RLS y sin acceso para roles API. Las reservas se serializan por grupo: usuarios,
Malls y procesos simultáneos compiten por la misma bolsa sin excederla. Hay un solo
trabajo activo por Mall. Las generaciones manuales mantienen el intervalo mínimo y
límite diario de solicitudes de la política existente, por Mall, para impedir
comparaciones costosas ilimitadas que produzcan diferenciales vacíos.

Se contabilizan el SQL generado sin comprimir y el ZIP transferido; cada descarga
posterior descuenta otra vez el ZIP. Es una medida conservadora del tráfico de
archivos, no el medidor general de los proveedores. Se reserva hasta dos veces el
máximo del archivo para generación y una vez para descarga almacenada. Los intentos
fallidos consumen presupuesto; los procesos interrumpidos conservan la reserva al
vencer su lease. No se factura un excedente. Esta política interna no cancela los
costos de infraestructura de la cuenta.

### Automáticos configurables

En **Backups → Backup SQL**, un administrador asignado al Mall puede activar o
pausar la generación diaria y elegir una hora entre 00:00 y 23:00, en Santo Domingo.
Se crea un completo inicial, se renueva al cambiar de mes y se genera un diferencial
por día. El primer día se crea el completo y luego el diferencial. Si no existe una
copia almacenada de la base vigente, el programador crea un completo recuperable
nuevo antes de generar más diferenciales.

Se conservan siete días de diferenciales y sus completos necesarios. La base vigente
se conserva mientras siga vigente; las anteriores, mientras tengan diferenciales
retenidos. La tabla de archivos muestra el ID de referencia para emparejarlos.
La recuperación sigue necesitando el completo original más **un** diferencial y las
dependencias globales descritas arriba, en un entorno de recuperación compatible.

El bucket dedicado `sql-backups` es privado y no tiene políticas para clientes. Los
ZIP se almacenan en fragmentos de 8 MB, dentro del límite por objeto del bucket,
sin cargar un archivo multi-GB en RAM ni modificar el bucket CSV. El backend
reconstruye el flujo con autenticación y reserva semanal. No se emiten URLs públicas
ni firmadas que permitan evadir la cuota. Se comprueban tamaños de fragmentos y el
total del archivo. El navegador mantiene el mecanismo Blob existente, que requiere
memoria suficiente para descargar archivos grandes.

El worker ejecuta el programador SQL en un proceso hijo separado del ciclo de
importación. Hay una instancia local y claims PostgreSQL de quince minutos para
evitar duplicaciones entre réplicas. Cada ejecución procesa hasta cuatro trabajos;
cada generación conserva el timeout de diez minutos. Las importaciones no esperan
al backup. Una pausa/cambio de hora durante la subida aborta la nueva base antes
del commit. Una subida completa puede recuperarse de los metadatos tras un fallo de
proceso; los fragmentos incompletos se eliminan al caducar.

### Activación

1. Aplicar `sql_backup_weekly_traffic` y `sql_backup_daily_schedules` después de las
   migraciones diferenciales. No incluyen IDs de clientes ni activan planes.
2. Crear el grupo en `traffic_plans`, asignar solo los Malls autorizados mediante
   `traffic_malls` y configurar sus horarios en `sql_schedules`.
3. API y worker: `ENABLE_SQL_BACKUP_WEEKLY_QUOTA=true`,
   `ENABLE_SCHEDULED_SQL_BACKUPS=true` y las variables existentes para backups SQL y
   diferenciales. El worker necesita el mismo `BACKUP_DATABASE_URL` (referencia de
   Railway al servicio API) y sus credenciales de Supabase. `Dockerfile.worker`
   incorpora el cliente PostgreSQL.
4. Habilitar el grupo y las programaciones. `next_run_at=now()` permite crear las
   bases iniciales en el siguiente ciclo. Luego se usa la hora elegida. Guardar el
   formulario programa la siguiente ocurrencia futura de esa hora.

Los Malls no asignados conservan la política anterior. La API exige permiso SQL y
pertenencia al Mall para consultar, configurar y descargar. Las cuotas se comprueban
en el servidor; los valores del navegador no pueden ampliarlas. La programación no
crea cobros, suscripciones ni enlaces de descarga fuera del control de tráfico.

# Restaurar desde CSV

En **Herramientas → Backup de importaciones → Restaurar desde CSV**, un administrador con acceso a Backups puede validar y restaurar los CSV que descarga el sistema. El servidor verifica el rol con datos de autorización propios; los permisos de solo descarga no habilitan restauración.

1. Seleccionar el Mall original y el tipo de archivo: Locales, Importadores API/locales, FTP/SFTP, Webservice o Ventas.
2. Seleccionar el CSV UTF-8 original, sin modificar sus columnas (se admite BOM).
3. Pulsar **Validar y previsualizar**. Revisar cantidades, filas omitidas y errores.
4. Pulsar **Confirmar restauración**. Se vuelven a validar los datos y duplicados antes de escribir.
5. Volver a validar para verificar que los registros existentes se omiten.

Orden de recuperación: **locales → configuraciones/importadores → ventas**. No se remapean identificadores entre Malls ni entre locales recreados con otro ID. Si el ID padre ya no existe, se indica el error para restaurar primero su backup. Se requiere una copia del Mall existente; los CSV no restauran Malls, usuarios, permisos, catálogos adicionales ni datos ausentes del archivo.

## Duplicados y datos existentes

- Locales: ID original o código interno dentro del Mall.
- Ventas: ID original y, cuando hay comprobante, local + fecha + número de transacción. Sin comprobante se utiliza el ID original, conservando registros legítimos sin número.
- Configuración de importador: se completa solo un local sin host, usuario, contraseña, mapeo ni constantes; no se modifica una conexión operativa.
- Conexiones compartidas FTP/SFTP: ID original o nombre dentro del Mall.
- Receptores ERP: ID original o local dentro del Mall.

Las escrituras nuevas usan `ignore_duplicates` y se respetan los índices únicos existentes. Un conflicto único concurrente se cuenta como omitido. Ningún CSV permite sobrescribir un registro existente. No se modifican los formatos de descarga ni el esquema de la base de datos.

## Credenciales y activación

Los exportadores omiten usuarios de conexión, contraseñas, tokens y secretos, y depuran JSON/URLs. No es posible recuperar esos datos desde estos CSV. Los importadores recuperados se guardan en **MANUAL**, las conexiones compartidas sin usuario/contraseña y los receptores ERP **deshabilitados**. Completar credenciales y revisar la configuración en su mantenimiento antes de habilitar operación automática. Los locales nuevos conservan el estado activo del CSV, pero tienen importación manual y `upsert_activo=false`.

## Límites y recuperación de errores

Máximo **5 MB y 2,000 filas** por archivo. Para backups mayores dividir por filas con un lector CSV, repitiendo la cabecera y respetando comillas y saltos de línea dentro de celdas. Un archivo vacío, con columnas distintas, Mall incorrecto, identificadores inválidos, fechas inválidas o importes no finitos no se aplica. Los importes se procesan con Decimal; los números de comprobante siguen siendo texto y conservan ceros iniciales. Se revierte exclusivamente el escape de fórmulas usado por el exportador.

La vista previa no escribe. Los errores de validación de filas bloquean todo el archivo. Las escrituras no constituyen una transacción global: un fallo de base de datos o una interrupción puede dejar una restauración parcial. La respuesta identifica filas fallidas sin revelar detalles internos. Volver a validar y aplicar el mismo archivo omite lo ya guardado. Mantener la sección abierta durante la restauración; cerrar el navegador no garantiza cancelar escrituras iniciadas en el servidor.

La recuperación no procesa archivos SFTP, no renombra archivos remotos, no activa programaciones y no modifica POS. No consume cuota de descarga.

## Verificación

Pruebas de ida y vuelta usan el exportador actual y una base simulada: ventas/locales/importadores, conexiones compartidas y receptores ERP, vista previa sin escritura, reintento, duplicados, aislamiento por Mall, autorización, límites, errores, importes negativos y escape de texto. No se restauran datos de producción como parte de las pruebas.

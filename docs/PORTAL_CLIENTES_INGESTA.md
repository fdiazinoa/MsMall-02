# Portal de clientes: ingesta de ventas

## Acceso y alcance

- Entrada: `/portal-cliente`, con el login y recuperación de contraseña existentes de Supabase Auth.
- Cada cuenta de cliente está vinculada a **un único local**. La página muestra su nombre y código como texto; el cliente no puede seleccionar ni enviar otro destino.
- El backend resuelve el destino exclusivamente desde `client_portal_grants.user_id`, después de verificar la sesión. La base impide dos vínculos para el mismo usuario.
- Crear las cuentas desde **Administración → Clientes del portal**. Se marcan mediante `app_metadata.portal_client`, que sólo puede editar el servidor. No asignarles roles internos ni membresías de mall; los endpoints administrativos existentes rechazan esas asignaciones para estas cuentas.
- Las cuentas externas se administran en Clientes del portal y se excluyen de la lista de Usuarios y Roles, reservada al personal interno.
- Las cuentas de portal ven sólo esta página y su historial. No se muestran navegación interna, dashboards ni credenciales FTP. El backend bloquea sus llamadas a rutas internas que utilizan la dependencia de autenticación principal.
- El administrador puede retirar el vínculo y asignar otro local. Retirar el vínculo bloquea inmediatamente nuevas cargas y consultas de historial, y elimina los mapeos vinculados; preserva la auditoría de cargas.
- Se mantiene el procesamiento FTP/SFTP. Los mapeos del portal se almacenan por usuario, local y estructura de columnas, separados de la configuración FTP.

## Archivos y flujo

1. Cargar o arrastrar un CSV/TXT, JSON o HTML (hasta 10 MB, 50,000 filas y 200 columnas).
2. Analizar: vista previa de cinco filas, sugerencias de mapeo y recuperación de mapeos guardados.
3. Mapear factura, fecha, bruto, impuestos y neto; hora opcional. Configurar formato de fecha y separador decimal.
4. Validar todas las filas sin escribir ventas. Las fechas y periodos cerrados usan el motor actual. No se importa un archivo con errores detectados en esta fase.
5. Confirmar: reutilizar el motor de ventas y su upsert por local/fecha/factura. Guardar el mapeo tras una carga sin errores y registrar el envío en historial propio y Monitor de Cargas.

El archivo debe contener exclusivamente ventas del local vinculado a la cuenta. Las columnas del archivo no pueden cambiar el local de destino.

### Formatos admitidos

- CSV/TXT delimitado por coma, punto y coma, tabulación o barra vertical; opción de primera fila con encabezados. Sin encabezados se generan `col_1`, `col_2`, etc. UTF-8/BOM o Windows-1252.
- JSON: lista de objetos, un objeto individual o un objeto con una única lista de objetos. Los objetos anidados generan rutas como `totals.gross`. Varias listas requieren exportar por separado la lista de ventas.
- HTML: tablas simples; elegir una tabla si hay varias. No se ejecutan scripts ni se renderiza el HTML del archivo. Se rechazan tablas anidadas y celdas combinadas. No se extraen reportes construidos por JavaScript ni se aplica OCR.
- Importes: números finitos, con agrupación de miles coherente con el separador decimal elegido. Las fechas ambiguas requieren escoger el formato correcto.

### Reintentos y errores operativos

Cada confirmación utiliza un identificador UUID estable. Un reintento con el mismo identificador y contenido devuelve el resultado registrado; un envío concurrente no procesa dos veces. El mismo identificador con contenido distinto se rechaza. Una nueva carga de las mismas facturas usa el upsert existente.

Los errores de infraestructura durante los lotes de escritura conservan las limitaciones del motor actual: puede haber escrituras parciales; la importación no es una transacción global. Si el proceso se interrumpe después de registrar el envío, el historial puede quedar `processing`. No se reprocesa automáticamente ese identificador: un operador debe revisar ventas y logs antes de iniciar otro envío. Los archivos originales no se conservan; se guardan nombre, huella y resultado. El historial muestra los últimos 30 envíos y hasta 100 errores por envío.

## Activación

1. Aplicar `supabase/migrations/20261117142242_client_ingestion_portal.sql` al proyecto Supabase correspondiente con el procedimiento de despliegue del proyecto. Crea tres tablas con RLS y acceso exclusivo `service_role`; no modifica tablas ni configuraciones FTP existentes.
2. Backend Railway: configurar `CLIENT_PORTAL_ENABLED=true`, con `SUPABASE_SERVICE_ROLE_KEY` disponible sólo en el servidor. Por defecto las rutas nuevas devuelven 404.
3. Frontend Vercel: configurar `VITE_CLIENT_PORTAL_ENABLED=true` y reconstruir para habilitar la gestión en Administración → Clientes del portal.
4. Crear una cuenta de cliente con su local, iniciar sesión en `/portal-cliente` y ejecutar una carga controlada. No se necesita un proveedor de autenticación nuevo.
5. Para desactivar las nuevas cargas, poner `CLIENT_PORTAL_ENABLED=false`; no borrar tablas ni datos. Retirar también el flag del frontend si se desea ocultar la administración.

La entrega en PR incluye código y migración. La migración y los flags **no se aplicaron a producción** durante el desarrollo.

## Verificación realizada

- Build Vite de producción correcto; conserva la advertencia existente sobre tamaño del bundle principal.
- Pruebas automatizadas del portal y regresiones FTP/autenticación: formatos, mapeos, validación sin escritura, acceso revocado, cuentas ajenas, aislamiento de historial, periodos cerrados, local resuelto por login aunque el navegador envíe otro, destino UUID con códigos duplicados, restricción de cuentas de portal y reintentos.
- Migración ejecutada en PostgreSQL local con tablas mínimas de referencia: RLS habilitado, roles `anon`/`authenticated` sin lectura/escritura, `service_role` con acceso, unicidad de usuario/local y eliminación de mapeos al retirar el vínculo.
- Navegador con sesión y respuestas simuladas: carga → mapeo → validación → confirmación. Revisión visual posterior: local fijo sin selector. No se usaron cuentas reales ni ventas de producción.
- TypeScript global produce los mismos 27 diagnósticos que `origin/main`, sin diagnósticos nuevos. Tres fallos de `test_sftp_file_listing_and_retry.py` y dos de `test_user_role_reassignment.py` también se reprodujeron en `origin/main`.
- Falta el smoke test real tras aplicar la migración y activar ambos despliegues.

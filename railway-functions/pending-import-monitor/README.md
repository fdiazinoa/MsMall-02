# Pending Import Monitor

Función programada de Railway para recuperar importaciones remotas que no encontraron archivo durante el ciclo regular.

- Cron en Railway (UTC): `0 0,15,18,21 * * *`
- Horario de República Dominicana: 8pm, 11am, 2pm y 5pm.
- Busca logs exitosos con `archivo = N/A` y el mensaje de archivo nuevo no encontrado.
- Consulta la carpeta real por FTP o SFTP, omite archivos ya importados y solicita al backend FastAPI procesar el archivo más reciente elegible.
- Registra cada revisión en `connection_runs` y `retry_attempts`.

## Variables requeridas

En la Function:

- `SUPABASE_URL`
- `SUPABASE_KEY` (solo para acceso backend a las tablas)
- `WORKER_API_URL=https://msmall-02-production.up.railway.app/api`, dirigido al servicio FastAPI `MsMall-02`
- `PENDING_IMPORT_MONITOR_TOKEN`, secreto aleatorio de al menos 32 caracteres
- `RESEND_API_KEY`, cuando las notificaciones por correo estén habilitadas

El servicio FastAPI `MsMall-02` debe tener exactamente el mismo
`PENDING_IMPORT_MONITOR_TOKEN`. Se puede generar uno con:

```bash
openssl rand -hex 32
```

La Function llama a `POST /api/v1/remote/execute-manual/internal` y envía el
secreto en `X-MsMall-Internal-Token`. No se debe enviar `SUPABASE_KEY` como
Bearer token de usuario.

Smoke test de autenticación, usando un `config_id` real y un archivo pendiente:

```bash
curl -i -X POST "https://msmall-02-production.up.railway.app/api/v1/remote/execute-manual/internal" \
  -H "Content-Type: application/json" \
  -H "X-MsMall-Internal-Token: <PENDING_IMPORT_MONITOR_TOKEN>" \
  -d '{"config_id":"<LOCAL_UUID>","filename":"<ARCHIVO>","request_id":"smoke-pending-monitor-001"}'
```

La respuesta y el código HTTP del worker quedan resumidos en
`connection_runs` y `retry_attempts`. Los resultados incluyen el marcador
`[outcome=recovered|still_pending|error]` para distinguir recuperación de una
simple revisión sin archivo.

## Sincronización

El archivo `index.tsx` es la fuente versionada. Para publicar una modificación validada:

```bash
railway functions push -p railway-functions/pending-import-monitor/index.tsx
```

Para verificar que la versión local coincide con Railway:

```bash
railway functions pull -p railway-functions/pending-import-monitor/index.tsx
```

## Destino y referencia del secreto

`ftp-import-worker` ejecuta `start_worker.sh` como proceso de fondo y no escucha HTTP.
No debe usarse como destino de `WORKER_API_URL`: produce errores de conexión aunque
el worker esté operativo. El endpoint interno está definido en `main.py` y lo sirve
`MsMall-02`. No es necesario reiniciar ni cambiar el worker para corregir esta ruta.

En las variables de `pending-import-monitor`, usa la referencia de Railway
`PENDING_IMPORT_MONITOR_TOKEN=${{MsMall-02.PENDING_IMPORT_MONITOR_TOKEN}}` para mantener
el secreto alineado con el backend, sin copiarlo ni incluirlo en Git.

Tras aplicar los cambios, inicia una sola ejecución del monitor y comprueba el
cierre del ciclo, las respuestas del endpoint interno y los logs de carga de los
archivos encontrados. Un mensaje de arranque o un despliegue exitoso por sí solos
no verifican el procesamiento. Una respuesta 401 sin token confirma que el endpoint
es accesible y que continúa protegido; no debe deshabilitarse su autenticación.

# Pending Import Monitor

Función programada de Railway para recuperar importaciones remotas que no encontraron archivo durante el ciclo regular.

- Cron en Railway (UTC): `0 0,15,18,21 * * *`
- Horario de República Dominicana: 8pm, 11am, 2pm y 5pm.
- Busca logs exitosos con `archivo = N/A` y el mensaje de archivo nuevo no encontrado.
- Consulta la carpeta real por FTP o SFTP, omite archivos ya importados y solicita al worker procesar el archivo más reciente elegible.
- Registra cada revisión en `connection_runs` y `retry_attempts`.

## Variables requeridas

En la Function:

- `SUPABASE_URL`
- `SUPABASE_KEY` (solo para acceso backend a las tablas)
- `WORKER_API_URL`, con formato `https://<servicio-worker>/api`
- `PENDING_IMPORT_MONITOR_TOKEN`, secreto aleatorio de al menos 32 caracteres
- `RESEND_API_KEY`, cuando las notificaciones por correo estén habilitadas

El servicio FastAPI/worker debe tener exactamente el mismo
`PENDING_IMPORT_MONITOR_TOKEN`. Se puede generar uno con:

```bash
openssl rand -hex 32
```

La Function llama a `POST /api/v1/remote/execute-manual/internal` y envía el
secreto en `X-MsMall-Internal-Token`. No se debe enviar `SUPABASE_KEY` como
Bearer token de usuario.

Smoke test de autenticación, usando un `config_id` real y un archivo pendiente:

```bash
curl -i -X POST "https://<servicio-worker>/api/v1/remote/execute-manual/internal" \
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

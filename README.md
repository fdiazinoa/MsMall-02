# MSMALL Audit Systems

Plataforma de Auditoría diseñada bajo estándares de escalabilidad SaaS, priorizando la integridad de los datos de ventas y la automatización de procesos de auditoría.

**Estado del Proyecto:** MVP Funcional (v1.0.2)
**Arquitectura:** React SPA + Backend FastAPI + PostgreSQL
**Ejecución actual:** frontend activo en **Vercel**.

## 0. Despliegue e Infraestructura
- **Frontend (SPA):** desplegado en **Vercel**.
- **Backend API + procesos programados:** ejecutados en **Railway**.
- **Worker/Cron de importación:** corridos en Railway para tareas programadas de SFTP/FTP.

### Scheduler (autoridad de cron)
- **Autoridad única recomendada:** `worker_importacion.py` (servicio worker en Railway).
- **API FastAPI:** el scheduler embebido queda deshabilitado por defecto y solo se activa con `ENABLE_API_SCHEDULER=true`.
- **Valor recomendado en producción:** `ENABLE_API_SCHEDULER=false`.
- **Polling recomendado:** `WORKER_POLL_SECONDS=300` para respetar ventanas `HH:MM`, repartir carga y evitar ráfagas simultáneas.
- **Balanceo:** usar `MAX_CONCURRENT_WORKERS`, `MAX_CONCURRENT_PER_HOST`, `HOURLY_STAGGER_MINUTES` y `MAX_FILES_PER_BATCH` para escalonar ejecuciones automáticas.
- **Nota de despliegue Railway:** mantener el loop automático únicamente en el servicio worker; la API conserva triggers manuales/endpoints.

## 1. Stack Tecnológico
- **Frontend:** React 18.3.1 con TypeScript.
- **Estilos:** Tailwind CSS.
- **Visualización de Datos:** Recharts.
- **Iconografía:** Lucide React.
- **Backend:** FastAPI (Python 3.9+ en `runtime.txt`).
- **Base de Datos:** PostgreSQL.

## 2. Módulos Funcionales
### A. Dashboard BI (Business Intelligence)
- KPIs en Tiempo Real: Ventas Brutas, Netas, Transacciones y Ticket Promedio.
- Gráficos Interactivos: Tendencia diaria y comparativa de Top 5 locales.

### B. Módulo de Importación Automatizada (FTP/SFTP)
- Protocolos Soportados: SFTP (SSH) y FTP estándar.
- Motor de Mapeo Dinámico: Vinculación de columnas externas con campos del sistema.
- Test de Conexión y Simulación de Sync.

### C. Auditoría y Reportabilidad de Ventas
- Tablero de Control: Vista detallada de transacciones auditadas.
- Cálculo Automático: Desglose de impuestos y neto.

### D. Mantenimiento de Locales y Contratos
- Gestión Contractual: Registro de m², responsables, % de Renta Variable.
- Inventario Físico: Clasificación por rubro, piso y Mall.

### E. Gestión de Usuarios y RBAC
- Roles activos en app: `admin`, `tic`, `auditor`.
- Seguridad: Panel de activación/desactivación y trazabilidad.

## 6. Notas de Implementación Actual
- El backend expone rutas tanto desde `main.py` como desde `routers/` (`recipes`, `comparisons`, `admin_tools`).
- El script operativo presente para worker es `start_worker.sh` (no existe `run.sh` en este repositorio).
- La versión declarada de la API en FastAPI es `1.0.0` (`main.py`), aunque el estado funcional del proyecto se documenta como MVP `v1.0.2`.
- Variables operativas relevantes:
  - `ENABLE_API_SCHEDULER=false` (default recomendado)
  - `WORKER_POLL_SECONDS`, `MAX_CONCURRENT_WORKERS`, `MAX_CONCURRENT_PER_HOST`, `HOURLY_STAGGER_MINUTES`, `MAX_FILES_PER_BATCH`
  - `CACHE_TTL_DASHBOARD`, `CACHE_TTL_RANKING`, `CACHE_TTL_HEATMAP`
  - `frecuencia_cron` / `hora_especifica` en configuración de locales (worker)

## 3. Arquitectura de Datos
Esquema relacional optimizado (`init.sql`):
- `malls`: Soporte multi-tenant con api_key únicas.
- `locales`: Relación 1:N con Malls.
- `ventas`: Tabla transaccional con índices en fecha.
- `import_configs`: Configuración de mapeo y conexión.

## 4. Seguridad e Integración
- **Autenticación por X-API-Key:** Para integraciones externas autorizadas.
- **Validación de Esquema:** Validación de encabezados CSV.
- **Cifrado:** Diseño para cifrado RSA-4096 de credenciales.

### PR-4: Operaciones sensibles movidas a backend (FastAPI)
- **Conexiones remotas (`remote_connections`)**: CRUD vía API backend con RBAC/tenant checks.
- **Secretos protegidos**: la API no devuelve `password` en claro (retorna `password=""` + `password_masked`/`has_password`).
- **Logs de carga (`logs_carga`)**: lectura y limpieza vía API backend (`/api/v1/load-logs`).
- **Reactivación de locales suspendidos**: endpoint backend para restablecer `processing_status` y `consecutive_failures`.
- **Compatibilidad**: se mantiene `/api/v1/audit/logs` como alias legacy para limpieza, mientras el frontend migra a `/api/v1/load-logs`.

#### Endpoints nuevos / seguros
- `GET /api/v1/remote-connections?mall_id=<uuid>`
- `POST /api/v1/remote-connections`
- `PATCH /api/v1/remote-connections/{id}`
- `DELETE /api/v1/remote-connections/{id}`
- `GET /api/v1/load-logs?mall_id=<uuid>&local_id=<uuid>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `DELETE /api/v1/load-logs?mall_id=<uuid>`
- `POST /api/v1/locales/{id}/reactivate-processing`

#### Rollout / compatibilidad
- Frontend `ImportManager`, `LoadMonitor` y `StoreMaintenance` ahora consumen estas operaciones sensibles vía backend (Bearer).
- Las rutas de importación manual y scheduler no se modifican en este PR.
- **CORS en backend (FastAPI):** en `production/staging` usar allowlist por variable de entorno (sin wildcard `*`).

### PR-5: Monitoreo y reintento formal de conexiones (FastAPI + worker)
- **Nuevo subsistema auditable:** tablas `connection_runs` y `retry_attempts` para trazabilidad de chequeos/reintentos.
- **Endpoints operativos:** status/failures/retry/retry-failed con RBAC y aislamiento por `mall_id`.
- **Clasificación estandarizada de errores:** `auth_error`, `timeout`, `endpoint_down`, `validation_error`, `unknown_error`.
- **Retry policy configurable:** `RETRY_MAX_ATTEMPTS`, `RETRY_COOLDOWN_SECONDS`, límite de batch por request.
- **Job nocturno en worker (sin tocar scheduler actual de importación):** ejecución condicional por `NIGHTLY_RETRY_ENABLED` y `NIGHTLY_RETRY_CRON`.
- **Observabilidad:** `system_health` con `CONNECTION_MONITOR_LAST_RUN`, `CONNECTION_MONITOR_LAST_SUCCESS`, `CONNECTION_MONITOR_LAST_ERROR`.

#### Endpoints PR-5
- `GET /api/v1/connections/status?mall_id=<uuid>`
- `GET /api/v1/connections/failures?mall_id=<uuid>&date=YYYY-MM-DD`
- `POST /api/v1/connections/{id}/retry`
- `POST /api/v1/connections/retry-failed?mall_id=<uuid>&date=YYYY-MM-DD`

#### Variables de entorno PR-5
- `RETRY_MAX_ATTEMPTS=3`
- `RETRY_COOLDOWN_SECONDS=300`
- `RETRY_BATCH_REQUEST_LIMIT=20`
- `NIGHTLY_RETRY_ENABLED=true`
- `NIGHTLY_RETRY_CRON=0 2 * * *` (UTC)

#### Flujo nocturno (worker)
1. El worker evalúa si el slot nocturno ya venció (`NIGHTLY_RETRY_CRON`) y si no se ejecutó aún.
2. Revisa `remote_connections`, registra `connection_runs` por conexión.
3. Si falla, intenta retry según policy y registra `retry_attempts`.
4. Actualiza `system_health` del monitor.

#### Rollback corto PR-5
1. Revert del merge commit en `develop`.
2. Redeploy API/worker en Railway al commit previo.
3. (Opcional) desactivar temporalmente monitor con `NIGHTLY_RETRY_ENABLED=false`.

### Configuración CORS (ejemplo)
```env
APP_ENV=production
CORS_ALLOW_ORIGINS=https://msmall.vercel.app,https://admin.tudominio.com
```

## 5. Roadmap
- Webhooks de Notificación (Slack/Email).
- Exportación PDF/Excel de informes firmados.
- Módulo de Conciliación automática.

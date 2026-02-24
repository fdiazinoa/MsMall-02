# MSMALL Audit Systems

Plataforma de Auditoría diseñada bajo estándares de escalabilidad SaaS, priorizando la integridad de los datos de ventas y la automatización de procesos de auditoría.

**Estado del Proyecto:** MVP Funcional (v1.0.2)
**Arquitectura:** React SPA + Backend FastAPI + PostgreSQL
**Ejecución actual:** frontend activo en **Vercel**.

## 0. Despliegue e Infraestructura
- **Frontend (SPA):** desplegado en **Vercel**.
- **Backend API + procesos programados:** ejecutados en **Railway**.
- **Worker/Cron de importación:** corridos en Railway para tareas horarias de SFTP/FTP.

### Scheduler (autoridad de cron)
- **Autoridad única recomendada:** `worker_importacion.py` (servicio worker en Railway).
- **API FastAPI:** el scheduler embebido queda deshabilitado por defecto y solo se activa con `ENABLE_API_SCHEDULER=true`.
- **Valor recomendado en producción:** `ENABLE_API_SCHEDULER=false`.
- **Nota de despliegue Railway:** mantener el cron/loop automático únicamente en el servicio worker; la API conserva triggers manuales/endpoints.

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
  - `CACHE_TTL_DASHBOARD`, `CACHE_TTL_RANKING`, `CACHE_TTL_HEATMAP`
  - `frecuencia_cron` / `hora_especifica` en configuración de locales (worker)

## 3. Arquitectura de Datos
Esquema relacional optimizado (`init.sql`):
- `malls`: Soporte multi-tenant con api_key únicas.
- `locales`: Relación 1:N con Malls.
- `ventas`: Tabla transaccional con índices en fecha.
- `import_configs`: Configuración de mapeo y conexión.

## 4. Seguridad e Integración
- **Autenticación por X-API-Key:** Para integración con sistemas POS externos.
- **Validación de Esquema:** Validación de encabezados CSV.
- **Cifrado:** Diseño para cifrado RSA-4096 de credenciales.

## 5. Roadmap
- Webhooks de Notificación (Slack/Email).
- Exportación PDF/Excel de informes firmados.
- Módulo de Conciliación automática.

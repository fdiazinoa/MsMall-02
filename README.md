# MSMALL Audit Systems

Plataforma de Auditoría diseñada bajo estándares de escalabilidad SaaS, priorizando la integridad de los datos de ventas y la automatización de procesos de auditoría.

**Estado del Proyecto:** MVP Funcional (v1.0.2)
**Arquitectura:** React SPA + Backend FastAPI + PostgreSQL

## 1. Stack Tecnológico
- **Frontend:** React 19 con TypeScript.
- **Estilos:** Tailwind CSS.
- **Visualización de Datos:** Recharts.
- **Iconografía:** Lucide React.
- **Backend:** FastAPI (Python 3.10+).
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
- Roles: `admin`, `auditor`, `mall_manager`.
- Seguridad: Panel de activación/desactivación y trazabilidad.

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

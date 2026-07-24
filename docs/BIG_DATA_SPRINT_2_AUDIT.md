# MSMALL Big Data — Sprint 2: auditoría y modelo operativo

## Matriz de capacidad

| Capacidad | Existe | Está conectada | Decisión |
| --- | ---: | ---: | --- |
| Proyección | Sí, en `analytics.py` y Finanzas | Legacy conectada | Conservarla intacta y crear un servicio Big Data independiente sobre agregados. |
| Evento | Sí, `operations_events` | No | Registrar hechos técnicos y comerciales normalizados desde el worker. |
| Hallazgo | Sí, `operational_findings` | No | Fuente oficial de condiciones que requieren revisión. |
| Observación | Sí, `operations_agent_observations` | No | Generar explicaciones determinísticas a partir de hallazgos. |
| Patrón | Sí, `operational_patterns` | No | Persistir recurrencias con evidencia y confianza. |
| Alerta | Sí, `alertas_inteligentes` | Parcial, Legacy | Mantener como canal de presentación/notificación; no duplicar hallazgos. |
| Operations Center | No en la rama | No | Crear una vista que consuma las entidades existentes y sus contratos reales. |
| Copilot | Sí, contexto comercial Legacy | Parcial | Extender el contexto con métricas Big Data controladas por flag. |

## Verificación de Operations Center en Git

- `components/OperationsCenter.tsx`, `services/operations_agent_service.py` y
  `services/operations_auditor_service.py` no están presentes en la base
  `develop` del Sprint 2.
- Sí aparecen en el historial de Git, entre otros, en los commits `845aa9b`,
  `d7fba61` y `57c81f5`.
- La navegación de `develop` tampoco registraba una pestaña operacional en
  `components/appTabs.ts`.
- La implementación de Sprint 2 reutiliza la estructura visual compacta que
  continúa siendo compatible, pero no recupera las consultas directas,
  reclamos no atómicos ni datos derivados del código anterior. La interfaz
  nueva consume exclusivamente contratos autenticados y persistencia real.

## Fuente oficial por concepto

- **Evento:** `operations_events`. Hecho inmutable de importación, refresh, calidad o cálculo.
- **Hallazgo:** `operational_findings`. Condición idempotente y atendible; su `fingerprint` evita duplicados.
- **Observación:** `operations_agent_observations`. Explicación sobre uno o varios hallazgos, con métricas fuente en `metadata`.
- **Patrón:** `operational_patterns`. Recurrencia histórica; nunca sustituye un hallazgo activo.
- **Alerta:** `alertas_inteligentes`. Notificación Legacy o presentada al usuario, derivada de hallazgos priorizados cuando corresponda.
- **Proyección:** contrato calculado desde agregados diarios/mensuales; se persiste como evidencia de hallazgo u observación solo cuando requiere atención.

## Límites de seguridad y activación

- `BIG_DATA_CORE` sigue desactivado por defecto y es requisito para toda lectura analítica.
- `BIG_DATA_FORECAST`, `BIG_DATA_OPERATIONS` y `BIG_DATA_COPILOT` son capacidades independientes y desactivadas por defecto.
- Todo contrato valida usuario, `mall_id` y flag antes de consultar agregados.
- El worker procesará hallazgos después de importaciones y refresh de agregados; fallos de observaciones o IA no bloquearán ventas.

## Estado inicial del Sprint

La base de producción ya contiene las entidades operacionales. Esta rama no crea un sistema paralelo: agregará contratos, servicio de proyección/anomalías, consumidor operacional, interfaz y pruebas sobre las tablas existentes.

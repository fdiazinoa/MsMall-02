# Certificación postactivación — Big Data Sprint 2

Fecha de certificación: 2026-07-24 (America/Santo_Domingo)
Decisión final: **NO_GO**
Alcance: validación postactivación de las capacidades Big Data en los ocho malls habilitados.

## 1. Resumen ejecutivo

La configuración de capacidades se confirmó correctamente: `BIG_DATA_CORE`,
`BIG_DATA_FORECAST`, `BIG_DATA_OPERATIONS` y `BIG_DATA_COPILOT` están activas
en exactamente los ocho malls del alcance y permanecen desactivadas en Plaza
360, el único mall adicional registrado.

La certificación se detuvo ante dos bloqueadores críticos observados mediante
consultas de solo lectura en producción:

1. Hay **1,089** ventas cuyo `ventas.mall_id` es **Sambil** mientras que el
   `local_id` asociado pertenece a **DownTown Mall**. Estas filas cubren
   2026-01-01 a 2026-04-28 y suman $6,981,779.55 bruto, $1,253,916.81 de
   impuestos y **$8,235,696.36 neto**.
2. La paridad mall/día no es exacta en DownTown, Mall Demo, Megacentro y
   Sambil. Como el refresco agrupa por `locales.mall_id`, la discrepancia de
   identidad anterior puede contaminar la atribución comercial aunque ciertos
   agregados coincidan al agrupar por local.

No se modificaron ventas, flags, RLS Legacy, colas ni agregados. No se hizo
merge ni se ocultaron controles bloqueados.

## 2. Estado reproducible

| Dato | Valor |
| --- | --- |
| Rama de certificación | `feature/big-data-sprint-2-postactivation-validation` |
| Base de código desplegada evaluada | `508b82794234ea1db8163603c70a71de8b7ef084` (`chore(git): merge develop into sprint two`) |
| Proyecto Supabase | `tqvdlceyuvngfftqobjv` — MercaSend Project, ACTIVE_HEALTHY |
| Migración más reciente aplicada | `20260724223708_big_data_sprint_2_controlled_validation` |
| API / worker | Railway; el repositorio declara API y worker separados. No había telemetría de Railway disponible para certificar revisiones de despliegue. |
| Frontend | `package.json` 0.0.0; versión de despliegue no verificable con la evidencia disponible. |

## 3. Flags e inventario

| Mall | CORE | FORECAST | OPERATIONS | COPILOT |
| --- | --- | --- | --- | --- |
| Mall Demo | PASS | PASS | PASS | PASS |
| Agora Mall SQD (Agora) | PASS | PASS | PASS | PASS |
| Blue Mall SDQ | PASS | PASS | PASS | PASS |
| Blue Mall Punto Cana (Punta Cana) | PASS | PASS | PASS | PASS |
| DownTown Mall | PASS | PASS | PASS | PASS |
| Megacentro Mall | PASS | PASS | PASS | PASS |
| Sambil | PASS | PASS | PASS | PASS |
| Santiago Center | PASS | PASS | PASS | PASS |
| Plaza 360 (fuera de alcance) | desactivado | desactivado | desactivado | desactivado |

Cada capacidad tiene `enabled_malls = 8`. Los nombres operativos se conservaron
tal como están en la base; las variantes de la solicitud se muestran entre
paréntesis cuando aplican.

| Mall | Fuente: primera / última fecha | Registros | Último agregado / watermark | Cola P / Proc / F | Última importación (UTC) |
| --- | --- | ---: | --- | --- | --- |
| Agora Mall SQD | 2025-04-29 / 2026-07-23 | 608,449 | 2026-07-23 / 2026-07-23 | 0 / 0 / 0 | 2026-07-24 21:44:37 |
| Blue Mall Punto Cana | 2017-08-16 / 2026-07-23 | 85,393 | 2026-07-23 / 2026-07-23 | 0 / 0 / 0 | 2026-07-25 00:04:34 |
| Blue Mall SDQ | 2024-01-11 / 2026-07-23 | 130,390 | 2026-07-23 / 2026-07-23 | 0 / 0 / 0 | 2026-07-24 12:32:52 |
| DownTown Mall | 2025-08-01 / 2027-03-15 | 126,064 | 2026-07-24 / 2026-07-24 | 0 / 0 / 0 | 2026-07-25 00:06:24 |
| Mall Demo | 2022-01-01 / 2026-07-24 | 8,461 | 2026-07-24 / 2026-07-24 | 0 / 0 / 0 | 2026-07-24 19:17:11 |
| Megacentro Mall | 2023-01-01 / 2026-12-03 | 261,770 | 2026-07-23 / 2026-07-24 | 0 / 0 / 0 | 2026-07-25 00:07:13 |
| Sambil | 2022-09-01 / 2026-12-07 | 538,724 | 2026-07-23 / 2026-07-24 | 0 / 0 / 0 | 2026-07-25 00:05:43 |
| Santiago Center | 2026-01-02 / 2026-07-23 | 33,419 | 2026-07-23 / 2026-07-23 | 0 / 0 / 0 | 2026-07-24 21:04:35 |

Las fechas fuente posteriores a la certificación (DownTown, Megacentro y
Sambil) se registran como anomalía de calidad temporal y no se normalizaron.

## 4. Incidente crítico: aislamiento cross-mall

La comprobación `ventas.mall_id <> locales.mall_id` devolvió 1,089 filas. La
única combinación afectada fue Sambil como mall de la venta y DownTown Mall
como mall del local. El procedimiento almacenado desplegado
`refresh_big_data_aggregates` filtra por `locales.mall_id`; por eso este caso
no puede considerarse aislado comercialmente aunque el agregado de nivel mall
coincida con la fuente agrupada por local.

| Mall origen en venta | Mall del local | Filas | Inicio | Fin | Neto |
| --- | --- | ---: | --- | --- | ---: |
| Sambil | DownTown Mall | 1,089 | 2026-01-01 | 2026-04-28 | $8,235,696.36 |

**Acción obligatoria antes de reanudar:** investigar la causa de identidad,
corregir las filas bajo un plan aprobado y reversible, reconstruir sólo los
períodos afectados, y repetir paridad y aislamiento. No se autoriza una
reconstrucción global.

## 5. Paridad postactivación

La comparación de fuente contra `big_data_daily_aggregates` usó el grano real
`grain='mall', dimension_key='mall'` y el mall de `locales`, que es el criterio
usado por el refresco desplegado.

| Mall | Días comparados | Días discrepantes | Máx. registros | Máx. bruto | Máx. impuestos | Máx. neto | Estado |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Agora Mall SQD | 329 | 0 | 0 | $0.00 | $0.00 | $0.00 | PASS técnico |
| Blue Mall Punto Cana | 2,329 | 0 | 0 | $0.00 | $0.00 | $0.00 | PASS técnico |
| Blue Mall SDQ | 567 | 0 | 0 | $0.00 | $0.00 | $0.00 | PASS técnico |
| DownTown Mall | 346 | 2 | 1 | $3,554.23 | $639.75 | $4,193.98 | FAIL |
| Mall Demo | 1,494 | 1,493 | 77 | $1,076,176.24 | $193,272.75 | $1,264,971.49 | FAIL |
| Megacentro Mall | 1,294 | 5 | 10 | $53,775.00 | $9,680.00 | $63,455.00 | FAIL |
| Sambil | 634 | 28 | 23 | $70,054.20 | $16,711.74 | $86,738.64 | FAIL |
| Santiago Center | 201 | 0 | 0 | $0.00 | $0.00 | $0.00 | PASS técnico |

Las diferencias no se atribuyen a notas de crédito: la condición de aceptación
es cero registros, cero importe y cero grupos discrepantes. La interfaz debe
mantener “Registros de venta” y “Promedio por registro”; no se evaluó como
ticket comercial.

## 6. Incrementalidad, Santiago y cola

El desencadenador desplegado encola una clave lógica única `(mall_id,
affected_date)` mediante `ON CONFLICT`; el reclamo usa `FOR UPDATE SKIP LOCKED`,
`claim_token`, reintento de trabajos vencidos a 15 minutos y el token previo no
puede completar un trabajo reclamado de nuevo. Esta es evidencia de código y
de definición desplegada, no sustituye la evidencia operacional completa.

`big_data_refresh_queue` tenía 76 trabajos, todos `completed`; no había
`pending`, `processing` ni `failed`. La duración total observada fue 133,459 ms
promedio y 302,844 ms máxima. No obstante, `operations_events` tenía 542
pendientes (el más antiguo: 2026-07-24 12:02 UTC) y 2 fallidos de DownTown;
por tanto Operations no queda certificado.

Santiago Center ya recibió ventas reales por WebService: el último log fue
2026-07-24 17:04:35 UTC, exitoso, con 10 registros; su watermark y último
agregado son 2026-07-23. La paridad agregada de 201 días es cero. Sin embargo,
la cadena completa, deduplicación y reentrega no se certifican después del
incidente de aislamiento: **BLOCKED**, no `ENABLED_PENDING_FIRST_WEBSERVICE_SALE`.

## 7. Controles no ejecutados después del incidente

Por la regla de detención inmediata no se ejecutaron smoke tests de UI por mall,
cambios rápidos de selector, contratos negativos, pruebas E2E, regresión
automatizada, ni un paquete visual 1366×768. No se declaran PASS por inspección
de código. Tampoco hubo acceso a telemetría Railway para CPU, memoria, locks o
versión de despliegue.

El benchmark histórico disponible se conserva sólo como antecedente: 1,000
filas con encolado 800.078 ms, sin encolado 696.644 ms, diferencia 103.434 ms
(14.85%). No es evidencia de rendimiento postactivación de importaciones reales.

## 8. Matriz final por mall

| Mall | Flags | Panel | Paridad | Incremental | Forecast | Operations | Copilot | Aislamiento | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Mall Demo | PASS | BLOCKED | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL | NO_GO |
| Agora | PASS | BLOCKED | PASS técnico | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL global | NO_GO |
| Blue Mall SDQ | PASS | BLOCKED | PASS técnico | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL global | NO_GO |
| Blue Mall Punta Cana | PASS | BLOCKED | PASS técnico | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL global | NO_GO |
| DownTown | PASS | BLOCKED | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL | NO_GO |
| Megacentro | PASS | BLOCKED | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL global | NO_GO |
| Sambil | PASS | BLOCKED | FAIL | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL | NO_GO |
| Santiago Center | PASS | BLOCKED | PASS técnico | BLOCKED | BLOCKED | BLOCKED | BLOCKED | FAIL global | NO_GO |

## 9. Matriz de controles

| Control | Estado | Evidencia | Bloqueador |
| --- | --- | --- | --- |
| Flags 8/8 | PASS | Cuatro flags con 8 malls habilitados; Plaza 360 desactivado | No |
| Smoke test multi-mall | BLOCKED | Detenido antes de UI | Incidente cross-mall |
| Paridad | FAIL | Discrepancias en 4 malls | Diferencias no cero |
| Incrementalidad | BLOCKED | Definición de trigger/worker, sin cadena completa postincidente | Incidente cross-mall |
| Aislamiento | FAIL | 1,089 ventas Sambil/DownTown inconsistentes | Cross-mall crítico |
| Worker y cola | FAIL | Cola Big Data estable; 542 eventos pendientes y 2 fallidos | Operations no drenado |
| Concurrencia y recuperación | BLOCKED | Mecanismo desplegado inspeccionado; sin nueva prueba operacional | Incidente cross-mall |
| Rendimiento | PARTIAL | Sólo benchmark histórico; sin telemetría postactivación | Sin SLO/telemetría real |
| Evidencia visual | BLOCKED | No ejecutada tras detención | Incidente cross-mall |
| Regresión automatizada | BLOCKED | No ejecutada tras detención | Incidente cross-mall |

## 10. Correcciones, rollback y siguiente paso

No se realizó corrección durante esta validación. No hay commit funcional que
revertir ni cambio de flags que deshacer. Si se confirma impacto de las 1,089
filas, el rollback operativo debe seguir un plan aprobado: aislar el flujo que
origina la identidad divergente, corregir exclusivamente las filas/períodos
afectados, refrescar únicamente Sambil y DownTown en 2026-01-01..2026-04-28 y
verificar paridad antes de reactivar la certificación. No modificar RLS Legacy
ni ejecutar backfill/reconstrucción global.

## Decisión final

### `NO_GO`

Existe evidencia de contaminación cross-mall y paridad no exacta. El PR debe
permanecer sin merge. La revalidación sólo puede comenzar después de documentar
la causa raíz y de resolver la inconsistencia de identidad de manera aprobada,
mínima y reversible.

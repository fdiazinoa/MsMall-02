# Big Data Sprint 1 — replicación y certificación progresiva multi-mall

Fecha: 2026-07-24  
Decisión: **PARTIAL_CERTIFICATION**  
Ámbito ejecutado: Santiago Center, Blue Mall SDQ y Agora Mall SQD.

## 1. Resumen ejecutivo

Se completó el backfill histórico de Sprint 1, un mall a la vez y en lotes
reanudables, para los tres perfiles requeridos. La paridad de mall, local/día,
categoría/día y mes fue exacta en los tres. No se modificó ninguna fila fuente
de `ventas`, no se ejecutó reconstrucción global y no se habilitó ningún flag
de Sprint 2 fuera de Mall Demo.

La certificación es parcial porque no se alteraron ventas reales para provocar
una importación incremental, ni se creó trabajo de cola sintético. Por tanto,
no hay evidencia operacional nueva de trigger + worker para estos tres malls.
Ningún mall recibe estado final `PASS` hasta observar esa incrementalidad en
una importación real autorizada.

## 2. Rama, commit y arquitectura

- Rama evaluada: `feature/big-data-sprint-2`.
- Commit base de ejecución: `9f1f9d5`.
- Sprint 1 usado: `20260724_big_data_sprint_1.sql` y
  `20260724_big_data_sprint_1_validation_fix.sql`.
- Función de backfill: `public.refresh_big_data_aggregates(mall, inicio, fin,
  'v1')`.
- Tablas: `big_data_daily_aggregates`, `big_data_monthly_aggregates`,
  `big_data_refresh_queue`, `big_data_refresh_runs` y
  `big_data_watermarks`.
- La clave primaria de agregados es `(mall_id, período, grain, dimension_key)`;
  una repetición elimina y recalcula el tramo, sin duplicar dimensiones.
- El trigger `trg_enqueue_big_data_refresh` solamente encola una fecha por
  `(mall_id, affected_date)`. El cálculo pesado se realiza fuera de la
  transacción de importación por el worker.

El backfill histórico se ejecutó internamente con la función Sprint 1 y no por
la cola, para mantener lotes explícitos y no competir con importaciones. La
función es aditiva respecto a `ventas`: sólo borra y reconstituye agregados del
rango del mall indicado.

## 3. Inventario inicial

| Mall | ID | Filas fuente | Período fuente | Locales | Agregados al inicio | Flags al inicio |
| --- | --- | ---: | --- | ---: | ---: | --- |
| Santiago Center | `71b9cf54-403c-4a26-b0be-247dc4690c37` | 33,419 | 2026-01-02 a 2026-07-23 | 111 | 0 | ninguno |
| Blue Mall SDQ | `16aaf5b1-0a96-4e7e-b826-d21def0ee5a3` | 130,390 | 2024-01-11 a 2026-07-23 | 182 | 0 | ninguno |
| Agora Mall SQD | `e6e42c16-c789-46e9-be86-37a22af05d93` | 608,449 | 2025-04-29 a 2026-07-23 | 124 | 0 | ninguno |

Las colas no tenían trabajos pendientes, procesando ni fallidos al comenzar.

## 4. Orden y backfill por mall

### Santiago Center — bajo volumen

Siete lotes mensuales (enero a julio de 2026). El mayor fue mayo, con 13,741
filas fuente. Duraciones de función: 91, 13, 16, 28, 79, 69 y 45 ms;
aproximadamente 341 ms acumulados para 33,419 filas. La repetición de enero
(209 filas) tomó 13 ms y mantuvo 30 filas de agregado mall, demostrando que
no duplicó resultados.

### Blue Mall SDQ — volumen medio

Once lotes trimestrales/de cierre (2024-01-01 a 2026-07-23). Duraciones de
función observadas: 72, 20, 20, 18, 17, 12, 86, 94, 5,660, 5,648 y 1,735 ms.
El acumulado de primera ejecución fue aproximadamente 13,382 ms para 130,390
filas; el lote repetido de 2024-Q1 tomó 109 ms y mantuvo 23 filas mall.

### Agora Mall SQD — alto volumen

Seis lotes trimestrales/de cierre (2025-04-01 a 2026-07-23). Duraciones:
82, 84, 22, 3,684, 3,099 y 1,728 ms. El acumulado de primera ejecución fue
aproximadamente 8,699 ms para 608,449 filas. La repetición del primer lote
tomó 198 ms y mantuvo 30 filas mall.

Las duraciones son del procedimiento SQL, no incluyen latencia del conector ni
constituyen un SLO de importación. No se observó error de función ni bloqueo
persistente durante los lotes. CPU, memoria y métricas de host no eran
observables desde este entorno.

## 5. Paridad numérica

Para cada rango completo se comparó la misma fuente `ventas JOIN locales` con
los agregados de grano mall. También se compararon grupos local/día,
categoría/día y mes. Se conservaron valores negativos y precisión decimal tal
como aparecen en la fuente.

| Mall | Dimensión | Diferencia registros | Diferencia bruto | Diferencia impuestos | Diferencia neto | Grupos discrepantes | Estado |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Santiago Center | Mall | 0 | $0.00 | $0.00 | $0.00 | 0 | PASS |
| Santiago Center | Local/día, categoría/día, mes | — | — | — | $0.00 | 0 | PASS |
| Blue Mall SDQ | Mall | 0 | $0.00 | $0.00 | $0.00 | 0 | PASS |
| Blue Mall SDQ | Local/día, categoría/día, mes | — | — | — | $0.00 | 0 | PASS |
| Agora Mall SQD | Mall | 0 | $0.00 | $0.00 | $0.00 | 0 | PASS |
| Agora Mall SQD | Local/día, categoría/día, mes | — | — | — | $0.00 | 0 | PASS |

## 6. Idempotencia, cola e incrementalidad

La repetición de un lote ya agregado en cada mall conservó una sola fila por
fecha/grano/dimensión, y la paridad no cambió. La clave primaria de agregados
impide duplicación. Después del backfill, no había trabajos de cola no
completados para los tres malls.

La ruta incremental está inspeccionada: `trg_enqueue_big_data_refresh` crea o
reenciende una única fila por mall+fecha sólo cuando `BIG_DATA_CORE` está
activo; `claim_big_data_refresh_queue` usa `FOR UPDATE SKIP LOCKED`, token de
claim, intentos y recuperación tras 15 minutos. No se insertó, actualizó ni
eliminó una venta real para disparar el trigger, ni se introdujo un trabajo
sintético. La incrementalidad observada por importación y el efecto real sobre
la prioridad del worker quedan **BLOCKED**.

## 7. Aislamiento y flags

La inspección de agregados terminó con las siguientes filas diarias y cero
filas de grano local cuyo `locales.mall_id` fuera distinto del mall del
agregado:

| Mall | Filas mall | Filas local | Filas categoría | Fuga cross-mall |
| --- | ---: | ---: | ---: | ---: |
| Santiago Center | 201 | 1,186 | 626 | 0 |
| Blue Mall SDQ | 567 | 4,318 | 1,369 | 0 |
| Agora Mall SQD | 329 | 18,393 | 2,184 | 0 |

`BIG_DATA_CORE` quedó activo únicamente para los tres malls certificados a
nivel histórico y Mall Demo. En Santiago, Blue y Agora,
`BIG_DATA_FORECAST`, `BIG_DATA_OPERATIONS` y `BIG_DATA_COPILOT` están en
`false`. Cada uno de esos flags Sprint 2 continúa habilitado en exactamente un
mall: Mall Demo.

Core expone el panel Sprint 1 para usuarios autorizados. Las rutas de resumen
ejecutivo/proyección exigen además `BIG_DATA_FORECAST`, y Operations/Copilot
exigen sus flags propios; por lo tanto no se expuso Sprint 2 en los tres malls
nuevos.

## 8. Pruebas y correcciones

| Control | Resultado |
| --- | --- |
| `python3 -m pytest -q tests` | 117 passed; warnings de dependencias y APIs obsoletas existentes |
| `npm run build` | PASS; warning histórico de bundle >500 kB |
| Paridad de backfill | PASS para los tres malls en las dimensiones documentadas |
| Repetición de lote | PASS para los tres malls |
| Incrementalidad mediante venta/importación real | BLOCKED; no se modificó fuente |
| Worker/cola de importación real | BLOCKED; no se introdujo trabajo sintético |

No fue necesaria una corrección de código. No hubo migración, cambio RLS,
alteración de Legacy, eliminación de ventas ni activación de Sprint 2.

## 9. Rendimiento y protección operativa

El trigger fue confirmado como encolador ligero; el refresco pesado se ejecuta
fuera de la transacción de importación. Los backfills manuales se hicieron uno
por uno, sin una reconstrucción global y sin dejar cola pendiente.

| Mall | Filas | Duración SQL acumulada | Filas/s aprox. | Lotes | Reintentos | Errores | Impacto |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Santiago Center | 33,419 | 341 ms | 98k | 7 | 0 | 0 | Sin bloqueo observado |
| Blue Mall SDQ | 130,390 | 13,382 ms | 9.7k | 11 | 0 | 0 | Sin bloqueo observado |
| Agora Mall SQD | 608,449 | 8,699 ms | 70k | 6 | 0 | 0 | Sin bloqueo observado |

Estas cifras no miden importaciones concurrentes, CPU, memoria ni latencia
end-to-end y no deben interpretarse como benchmark comercial.

## 10. Rollback

1. Desactivar `BIG_DATA_CORE` sólo para el mall que deba retirarse.
2. Mantener `BIG_DATA_FORECAST`, `BIG_DATA_OPERATIONS` y `BIG_DATA_COPILOT`
   apagados fuera de Mall Demo.
3. Conservar agregados, queue y watermarks como evidencia; no tocar `ventas`.
4. Si un rango requiere repetirse, ejecutar de nuevo sólo ese mall y fechas:
   el refresco reemplaza de forma idempotente sus agregados.

## 11. Matriz final

| Mall | Backfill | Paridad | Incremental | Idempotencia | Aislamiento | Rendimiento | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Santiago Center | PASS | PASS | BLOCKED | PASS | PASS | PASS limitado | BLOCKED |
| Blue Mall SDQ | PASS | PASS | BLOCKED | PASS | PASS | PASS limitado | BLOCKED |
| Agora Mall SQD | PASS | PASS | BLOCKED | PASS | PASS | PASS limitado | BLOCKED |

## Decisión y siguiente paso

**PARTIAL_CERTIFICATION.** El histórico y la paridad de los tres perfiles
quedaron demostrados, pero ninguno puede certificarse integralmente sin una
importación incremental observada por el trigger y worker. La recomendación
concreta para retomar Sprint 2 es esperar una importación real de cada mall
Core habilitado, registrar su trabajo de cola y paridad posterior, y sólo
entonces repetir la certificación final de Sprint 2. No habilitar Forecast,
Operations ni Copilot fuera de Mall Demo y no hacer merge del PR.

# Certificación operativa final — Big Data Sprint 2

Fecha de certificación: 2026-07-24  
Decisión final: **NO_GO**  
PR: [#299](https://github.com/fdiazinoa/MsMall-02/pull/299) — debe permanecer en borrador.

## 1. Resumen ejecutivo

La validación controlada confirma que el panel, las proyecciones con datos
insuficientes, Operations Center, observaciones, Copilot Big Data e
idempotencia de hallazgos funcionan en el piloto. La paridad de ventas se
confirmó con datos reales para un mall alto, medio y bajo, la semántica de
notas de crédito está cerrada y la concurrencia de dos conexiones PostgreSQL
fue ejecutada. Además, la ruta real de ingesta CSV → cola → worker → agregado
Big Data se validó sobre Mall Demo. Persisten controles de rendimiento y de
evidencia visual integral; por tanto, el PR **no puede pasar a listo para
merge**.

No se hizo merge, no se activó otro mall, no se modificó RLS Legacy, no se
reconstruyeron agregados globales y no se alteraron ventas reales durante esta
certificación.

## 2. Rama, commits y entorno

- Rama: `feature/big-data-sprint-2`.
- Commit evaluado: `2151982fff6f4568a598df007043c9932fc0a699`.
- Corrección funcional incluida: `a473e22` dirige preguntas mensuales de
  ventas del Copilot al contexto Big Data.
- Entorno: proyecto Supabase principal `tqvdlceyuvngfftqobjv`, con piloto
  controlado en Mall Demo (`ce12312e-220d-4200-aa36-a959bf7d271c`).
- API controlada desplegada: Railway
  `b2d2b7a8-28e8-4f93-ae5f-d60dabac77cc`.

## 3. Configuración segura de flags y aislamiento

La ausencia del flag es desactivación y los contratos validan `mall_id` y
capacidad. La consulta productiva confirmó que cada uno de los flags
`BIG_DATA_CORE`, `BIG_DATA_FORECAST`, `BIG_DATA_OPERATIONS` y
`BIG_DATA_COPILOT` está habilitado en exactamente **un** mall: Mall Demo.

Malls con datos fuente y sin flags habilitados incluyen Agora Mall SQD
(608,449 filas), Blue Mall SDQ (130,390) y Santiago Center (33,419). No se
activaron para ejecutar certificación.

## 4. Paridad numérica multi-mall

### Resultado ejecutado

La consulta de solo lectura del 2026-07-25 confirmó que ya existen agregados
Sprint 1 para los perfiles seleccionados. Se comparó la fuente `ventas` contra
los agregados Big Data para el 2026-07-23 y para el mes parcial del 1 al 23 de
julio; todas las diferencias son absolutas y porcentualmente cero.

| Escenario | Fuente | Big Data | Diferencia | Resultado |
| --- | ---: | ---: | ---: | --- |
| Mall Demo, 2026-07-24, registros | 6 | 6 | 0 | PASS parcial |
| Mall Demo, ventas brutas | $3,856.00 | $3,856.00 | $0.00 | PASS parcial |
| Mall Demo, impuestos | $694.08 | $694.08 | $0.00 | PASS parcial |
| Mall Demo, ventas netas | $3,161.92 | $3,161.92 | $0.00 | PASS parcial |
| Mall Demo, local Zara Demo | 6 / $3,161.92 netas | 6 / $3,161.92 netas | 0 / $0.00 | PASS parcial |
| Mall Demo, categoría MODA | 6 / $3,161.92 netas | 6 / $3,161.92 netas | 0 / $0.00 | PASS parcial |
| Agora Mall SQD — día 2026-07-23 | 767 / $4,485,065.30 netas | 767 / $4,485,065.30 netas | $0.00 / 0.00% | PASS |
| Blue Mall SDQ — día 2026-07-23 | 35 / $209,092.58 netas | 35 / $209,092.58 netas | $0.00 / 0.00% | PASS |
| Santiago Center — día 2026-07-23 | 358 / $1,653,658.18 netas | 358 / $1,653,658.18 netas | $0.00 / 0.00% | PASS |
| Agora Mall SQD — 1–23 jul. 2026 | 98,830 / $848,848,078.60 netas | 98,830 / $848,848,078.60 netas | $0.00 / 0.00% | PASS |
| Blue Mall SDQ — 1–23 jul. 2026 | 4,490 / $112,976,017.83 netas | 4,490 / $112,976,017.83 netas | $0.00 / 0.00% | PASS |
| Santiago Center — 1–23 jul. 2026 | 6,498 / $26,777,608.16 netas | 6,498 / $26,777,608.16 netas | $0.00 / 0.00% | PASS |
| Locales por día — Agora / Blue / Santiago | 20 / 1 / 12 grupos | mismos grupos y valores | 0 grupos / $0.00 | PASS |
| Categorías por día — Agora / Blue / Santiago | 9 / 1 / 6 grupos | mismos grupos y valores | 0 grupos / $0.00 | PASS |

También se obtuvo diferencia cero para bruto e impuestos en los seis controles
mall/día y mall/mes. Julio es un período incompleto y se conserva como tal.

### Correcciones incrementales controladas

Con una venta sintética, identificada y eliminada antes de finalizar, se validó
el encargo incremental de correcciones. La fila no dejó ventas ni colas de
prueba.

| Caso | Resultado |
| --- | --- |
| Inserción | Una fila creó una única fila `pending` en la cola. |
| Reingesta / corrección de importe | El trabajo volvió a `pending` y su `claim_token` quedó en `NULL`. |
| Cambio de fecha | Se encolaron los dos períodos: origen y destino. |
| Cambio de local dentro del mall | El período afectado permaneció encolado para reconstrucción. |
| Cambio de mall y local | Se encolaron tres claves: dos períodos de Mall Demo y el período destino de Agora. |
| Limpieza | 0 ventas y 0 filas de cola sintéticas. |

La reclasificación histórica no pudo certificarse: las tablas
`commercial_taxonomy`, `local_commercial_classifications` y
`local_classification_history` están vacías en el entorno. Además, el refresco
actual usa la clasificación vigente, no un intervalo histórico de vigencia. No
se debe declarar soporte histórico hasta implementar ese mantenimiento y
probarlo con categorías reales. La migración aditiva
`20260725_big_data_reclassification_history.sql` fue aplicada y validada con
un fixture aislado: la reclasificación encoló 2 días afectados y reconstruyó
el 2000-01-10 únicamente en Categoría C ($100) y el 2000-01-20 únicamente en
Categoría B ($200). No se dejó ninguna venta, categoría, agregado ni cola de
prueba. La paridad queda **PARTIAL** sólo por la cobertura temporal de los
casos, no por reclasificación.

### Ingesta de aplicación de extremo a extremo

Se cargó desde la interfaz CSV de Mall Demo un comprobante controlado para el
local `DEMO-514`. La aplicación informó **1 registro procesado**. Al tratarse
de una reingesta de una factura existente, el conteo se conservó en 6 y el
importe corrigió el agregado; no se generó una séptima fila. El trabajo de cola
`de29462a-ad2f-411e-8ce8-624da1cd7a61` pasó de `pending` a `completed` en el
siguiente ciclo del worker, sin error. La comparación final para 2026-07-24
fue exactamente igual entre fuente y agregado: 6 registros, $3,856.00 brutos,
$694.08 de impuestos y $3,161.92 netos (diferencia $0.00). Esta evidencia
cubre el flujo real de importador, trigger/cola, worker y actualización
incremental; no sustituye la telemetría de rendimiento de infraestructura.

## 5. Semántica de registros, ventas y notas de crédito

### Definición técnica actual

`refresh_big_data_aggregates` usa `count(*)` para `transaction_count` y para
`records_processed`. Por ello la unidad técnica de Big Data es **fila de
`ventas`**, no una transacción comercial demostrada. El panel Sprint 2 la
expone como **“Registros de venta”** y calcula **“Promedio por registro”**.

Fórmula técnica actual:

```
promedio_por_registro = sum(total_neto) / count(*)
```

La API Legacy todavía usa `ticket_average = sales_net / transaction_count` en
algunos contratos, y el contexto comercial Legacy usa bruto por fila. No se
modificaron porque la certificación no autoriza cambiar semántica por
inferencia.

### Evidencia real de `ventas`

| Medida | Resultado |
| --- | ---: |
| Filas totales | 1,792,670 |
| Filas con `factura_no` no vacío | 1,792,065 |
| Facturas distintas por `local_id + fecha + factura_no` | 1,792,065 |
| Grupos de factura repetidos | 0 |
| Máximo de filas por grupo de factura | 1 |
| Filas sin factura | 543 |
| Filas con bruto o neto negativo | 13,132 |
| Comprobantes explícitamente parecidos a crédito/anulación | 0 |

Existen días con hasta 1,121 filas de un mismo local y 60 días donde filas e
identificadores de factura no coinciden. La decisión comercial del 2026-07-24
define toda fila negativa como **nota de crédito**: debe rebajar ventas netas,
brutas e impuestos del mismo período y dimensión. `sum(total_neto)` ya aplica
esta regla; no requiere migración ni reconstrucción. La métrica visible se
mantiene como **Registros de venta** y el promedio como **Promedio por
registro**. La semántica de ticket/transacción comercial sigue sin certificarse
porque no existe una regla de agrupación de comprobantes.

## 6. Trigger, cola y benchmark de importación

El trigger real `trg_enqueue_big_data_refresh` es `AFTER INSERT OR DELETE OR
UPDATE` sobre `ventas`. Su función solamente verifica `BIG_DATA_CORE` e inserta
o actualiza una fila `(mall_id, affected_date)` de
`big_data_refresh_queue`; no recalcula agregados dentro de la transacción de
importación. El worker reclama después la cola con `FOR UPDATE SKIP LOCKED` y
ejecuta `refresh_big_data_aggregates` fuera del carril de importación.

Se ejecutó un benchmark controlado en Mall Demo con 1,000 filas sintéticas de
fecha histórica, identificadas y eliminadas dentro de la misma ejecución. No
quedaron ventas ni filas de cola de prueba. Para proteger producción, el rol de
base no permite desactivar `session_replication_role`; el comparativo sin
encolado se realizó desactivando `BIG_DATA_CORE` sólo dentro de la operación y
restaurándolo antes de terminar.

| Caso | Filas | Duración | Cola final |
| --- | ---: | ---: | ---: |
| Con encolado Big Data | 1,000 | 800.078 ms | 0 filas de prueba |
| Sin encolado Big Data | 1,000 | 696.644 ms | 0 filas de prueba |

El impacto observado fue **103.434 ms (14.85%)**. No se observaron bloqueos ni
esperas; no hubo métrica directa de CPU disponible desde el entorno. El
resultado demuestra que el trigger sólo agrega encolado y no ejecuta la
reconstrucción en la importación. Falta repetir la prueba con una importación
de aplicación completa y una métrica de CPU/base para convertirla en una
certificación final de rendimiento; el control queda **PARTIAL**.

## 7. Worker, concurrencia y recuperación

Evidencia existente:

- `claim_big_data_refresh_queue` y `claim_operations_events` usan `FOR UPDATE
  SKIP LOCKED`, `claim_token`, contador de intentos y timeout de 15 minutos.
- El worker corre importaciones antes de agregados, anomalías, observaciones y
  patrones.
- Dos ejecuciones reales consecutivas de anomalías para Mall Demo completaron:
  376 ms a las 23:06 UTC y 343 ms a las 23:11 UTC; ambas reportaron 1 elemento.
- Persistió un solo hallazgo `DATA_INCOMPLETE` con fingerprint
  `0740f3d6861e6735dc2b2657df645806e24fd1160f57dc80b29b4e1a2923e55d`.
- No había eventos `PROCESSING` vencidos al momento de la inspección.

Se ejecutó una prueba controlada sobre dos conexiones PostgreSQL independientes
(backend PID `3367537` y `3367538`) y filas sintéticas de Mall Demo con fechas
históricas. No se tocaron ventas reales.

| Caso | Resultado |
| --- | --- |
| Reclamo simultáneo | Dos conexiones llamaron `claim_big_data_refresh_queue(1)`: una recibió la fila `691e57d5-9772-480f-9bec-d4287c9fe3b9` con token `79abe5da-d005-4ff8-8715-deb0aabf54d5`; la otra recibió 0 filas. |
| Reencolado durante proceso | Al borrar el token y devolver el trabajo a `pending`, la actualización de finalización con el token anterior devolvió 0 filas. |
| Worker abandonado | Una fila `processing` con `started_at` de 16 minutos fue reclamada de nuevo; `attempts` pasó de 1 a 2 y recibió el token `f4619f37-6545-407b-874d-e3d046566cd9`. |
| Reinicio / propietario anterior | La finalización con el token abandonado `22222222-2222-4222-8222-222222222222` devolvió 0 filas; no pudo sobrescribir al nuevo propietario. |

La limpieza final confirmó 0 filas de cola de prueba, 0 agregados diarios o
mensuales sintéticos y watermark de Mall Demo sin cambio (`2026-07-24`). La
concurrencia de reclamo, reencolado y recuperación queda **PASS**. Falta una
prueba de apagado físico de un proceso de worker durante un refresco largo, que
se conserva como riesgo operativo de menor prioridad.

## 8. Validación visual

En el preview autenticado de Mall Demo se verificó:

- Panel Big Data con estado “El período requiere completar información”.
- Cobertura cercana al 4%, período incompleto y proyección “Datos
  insuficientes”.
- Tras la reingesta controlada: $3,161.92 netos, 6 registros y promedio por
  registro $526.99, idénticos al agregado final.
- Ingesta CSV que mostró “Procesado: 1 registros” antes del ciclo del worker.
- Operations Center con hallazgo `DATA_INCOMPLETE`, severidad HIGH y texto que
  evita afirmar caída comercial.
- Copilot Big Data con período, cobertura y estado `DATA_INCOMPLETE`, sin
  atribuir una caída comercial a un período incompleto.
- Cambio desde otro mall a Mall Demo sin conservar el error ni la selección
  anterior, tras la corrección `3ca844c`.

No se reunió un paquete persistente de capturas 1366×768 para todos los estados
solicitados, ni fue posible mostrar perfil 360° con datos útiles ni cambio
rápido entre dos malls analíticos habilitados. El control visual completo queda
**PARTIAL**; la evidencia navegada confirma los estados esenciales, pero no
sustituye el paquete final requerido para cerrar el PR.

## 9. Pruebas ejecutadas

| Comando | Resultado |
| --- | --- |
| `python3 -m pytest -q tests` | 121 passed, 85 warnings de dependencias/obsolescencias existentes |
| `npm run build` | PASS; warning existente por bundle de 1.32 MB (>500 kB) |
| `python3 -m pytest -q tests/test_big_data_sprint_two_contract.py` | 8 passed durante la corrección del Copilot |

## 10. Correcciones realizadas durante el piloto

| Commit | Corrección | Resultado |
| --- | --- | --- |
| `d550a25` | Permite `BIG_DATA_ANOMALY` en el constraint de fuente de hallazgos. | El detector persistió `DATA_INCOMPLETE`. |
| `599a999` | Restaura Dockerfile del worker de Railway. | Worker desplegado y ejecutó detección. |
| `3ca844c` | Evita recarga al cambiar de mall. | El selector conserva el mall nuevo. |
| `a473e22` | Enruta preguntas mensuales de ventas al Copilot Big Data. | Respuesta incluye cobertura y estado incompleto. |

## 11. Riesgos residuales y rollback

Riesgos bloqueantes: el benchmark aún no dispone de telemetría CPU/base ni de
una comparación completa de importación masiva de aplicación; la paridad debe
ampliarse a más fechas y períodos; y falta el paquete visual integral. La
transacción comercial no se infiere: la interfaz continúa usando “Registros de
venta”, y la concurrencia/recuperación de cola sí tienen prueba real.

Rollback del piloto:

1. Desactivar en Mall Demo `BIG_DATA_COPILOT`, `BIG_DATA_OPERATIONS`,
   `BIG_DATA_FORECAST` y `BIG_DATA_CORE`.
2. Revertir el despliegue API/worker al commit anterior conocido y conservar
   flags apagados.
3. No borrar eventos, hallazgos ni observaciones: son evidencia auditable.
4. Si se revierte código, revertir commits de forma convencional; nunca hacer
   push directo a `main`.

## 12. Matriz final

| Control | Estado | Evidencia | Bloqueador |
| --- | --- | --- | --- |
| Paridad multi-mall | PARTIAL | Paridad exacta diaria y mensual parcial en Agora, Blue Mall SDQ y Santiago; correcciones y reclasificación histórica con una sola categoría por día validadas | Falta ampliar la cobertura temporal de paridad, no hay diferencia observada |
| Semántica de ventas y registros | PASS | Notas de crédito definidas como importes negativos que rebajan ventas; `count(*)` se presenta como registros de venta | Ticket comercial no se expone ni se infiere |
| Benchmark de importación | PARTIAL | 1,000 filas: 800.078 ms con encolado vs. 696.644 ms sin encolado; +14.85%; y una reingesta CSV real completó cola, worker y paridad exacta | Falta comparación masiva completa y telemetría de CPU/base |
| Concurrencia de workers | PASS | Dos conexiones PostgreSQL reales; una sola obtuvo el trabajo; token único | Ninguno observado |
| Recuperación de trabajos | PASS | Abandono >15 min recuperado, attempts 1→2 y token anterior rechazado | Falta apagado físico de proceso en refresco largo como riesgo menor |
| Idempotencia de hallazgos | PASS parcial | Dos ejecuciones reales, un fingerprint lógico | No sustituye concurrencia de dos workers |
| Validación visual | PARTIAL | Panel, importación CSV, Operations, Copilot y cambio entre mall habilitado/no habilitado verificados | Paquete persistente, perfil 360° y cambio rápido entre dos malls habilitados |
| Flags y aislamiento | PASS | Cada flag Sprint 2 activo en un único mall, Mall Demo | Ninguno observado |
| Regresión automatizada | PASS | 121 tests y build exitosos | Warning histórico de tamaño de bundle |

## Decisión

**NO_GO.** Los controles parciales siguen siendo requisitos explícitos previos
a merge. El siguiente paso recomendado es ejecutar una importación representativa
con telemetría de Railway/Supabase y completar el paquete visual, mientras se
amplía la paridad a fechas adicionales. Hasta entonces, mantener PR #299 en
borrador y Sprint 2 limitado a Mall Demo.

# Certificación operativa final — Big Data Sprint 2

Fecha de certificación: 2026-07-24  
Decisión final: **NO_GO**  
PR: [#299](https://github.com/fdiazinoa/MsMall-02/pull/299) — debe permanecer en borrador.

## 1. Resumen ejecutivo

La validación controlada en Mall Demo confirma que el panel, las proyecciones
con datos insuficientes, Operations Center, observaciones, Copilot Big Data e
idempotencia de hallazgos funcionan en el piloto. No obstante, no es posible
demostrar los controles obligatorios de paridad multi-mall, semántica comercial
de transacción, benchmark comparable de importación, concurrencia de dos
workers ni recuperación real de trabajos abandonados bajo las restricciones
vigentes. Por tanto, el PR **no puede pasar a listo para merge**.

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

Sólo Mall Demo posee agregados Big Data: 3 filas diarias, para 2026-07-24.
Los perfiles alto, medio y bajo existen en `ventas`, pero sus agregados no
existen; crear o refrescar agregados para ellos exigiría habilitar flags o
reconstruir datos fuera del piloto, prohibido por esta certificación.

| Escenario | Fuente | Big Data | Diferencia | Resultado |
| --- | ---: | ---: | ---: | --- |
| Mall Demo, 2026-07-24, registros | 6 | 6 | 0 | PASS parcial |
| Mall Demo, ventas brutas | $3,976.00 | $3,976.00 | $0.00 | PASS parcial |
| Mall Demo, impuestos | $715.68 | $715.68 | $0.00 | PASS parcial |
| Mall Demo, ventas netas | $3,260.32 | $3,260.32 | $0.00 | PASS parcial |
| Mall Demo, local Zara Demo | 6 / $3,260.32 netas | 6 / $3,260.32 netas | 0 / $0.00 | PASS parcial |
| Mall Demo, categoría MODA | 6 / $3,260.32 netas | 6 / $3,260.32 netas | 0 / $0.00 | PASS parcial |
| Alto: Agora Mall SQD | 608,449 filas fuente | sin agregados | no comparable | BLOCKED |
| Medio: Blue Mall SDQ | 130,390 filas fuente | sin agregados | no comparable | BLOCKED |
| Bajo: Santiago Center | 33,419 filas fuente | sin agregados | no comparable | BLOCKED |

No se certificaron período completo, reingesta/duplicados, incrementalidad o
paridad mensual multi-mall. El control completo queda **BLOCKED**, no PASS.

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

No se ejecutó un benchmark sin/con trigger con el mismo dataset: exigiría
desactivar temporalmente el trigger o reimportar datos comparables, lo que
alteraría datos y condiciones reales. No hay SLO previo para convertir una
medición aislada en aprobación. El control queda **BLOCKED**.

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

No se ejecutaron dos workers independientes compitiendo por el mismo trabajo,
no se interrumpió un worker y no se esperó un timeout sobre un trabajo de
prueba. Crear eventos/colas sintéticos o un segundo servicio de worker en el
entorno principal excedería la autorización y podría interferir con la
operación. Concurrencia y recuperación quedan **BLOCKED**; la idempotencia de
hallazgos sí tiene evidencia real limitada.

## 8. Validación visual

En el preview autenticado de Mall Demo se verificó:

- Panel Big Data con estado “El período requiere completar información”.
- Cobertura 4.2%, 23 días incompletos y proyección “Datos insuficientes”.
- Valores visibles: $3,260.32 netos, 6 registros y promedio por registro
  $543.39.
- Operations Center con hallazgo `DATA_INCOMPLETE`, severidad HIGH y texto que
  evita afirmar caída comercial.
- Copilot Big Data con período, acumulado $3,260.32, un día con datos,
  cobertura 4.17% y `DATA_INCOMPLETE`.
- Cambio desde otro mall a Mall Demo sin conservar el error ni la selección
  anterior, tras la corrección `3ca844c`.

No se reunió un paquete persistente de capturas 1366×768 para todos los estados
solicitados, ni fue posible mostrar perfil 360° con datos útiles, estado vacío
de otro mall con agregados o cambio rápido entre dos malls analíticos. El
control visual completo queda **BLOCKED**.

## 9. Pruebas ejecutadas

| Comando | Resultado |
| --- | --- |
| `python3 -m pytest -q tests` | 117 passed, 83 warnings de dependencias/obsolescencias existentes |
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

Riesgos bloqueantes: paridad multi-mall no demostrada, definición comercial de
transacción pendiente, benchmark sin evidencia comparable, concurrencia y
recuperación sin prueba real, y evidencia visual incompleta.

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
| Paridad multi-mall | BLOCKED | Paridad exacta diaria de Mall Demo; cero agregados en alto/medio/bajo | No se permite activar/reconstruir fuera del piloto |
| Semántica de ventas y registros | PASS | Notas de crédito definidas como importes negativos que rebajan ventas; `count(*)` se presenta como registros de venta | Ticket comercial no se expone ni se infiere |
| Benchmark de importación | BLOCKED | Trigger sólo encola; sin medición comparable | No se puede reimportar/alternar trigger sin afectar condiciones reales |
| Concurrencia de workers | BLOCKED | Claim seguro inspeccionado; no hubo dos workers reales | Falta infraestructura aislada o autorización específica |
| Recuperación de trabajos | BLOCKED | Timeout de 15 min inspeccionado; 0 eventos vencidos | No se creó ni abandonó trabajo de prueba |
| Idempotencia de hallazgos | PASS parcial | Dos ejecuciones reales, un fingerprint lógico | No sustituye concurrencia de dos workers |
| Validación visual | BLOCKED | Panel, Operations y Copilot vistos en Mall Demo | Paquete de evidencias y escenarios faltantes |
| Flags y aislamiento | PASS | Cada flag Sprint 2 activo en un único mall, Mall Demo | Ninguno observado |
| Regresión automatizada | PASS | 117 tests y build exitosos | Warning histórico de tamaño de bundle |

## Decisión

**NO_GO.** Los controles bloqueados son requisitos explícitos previos a merge.
El siguiente paso recomendado es preparar un entorno integrado aislado o
autorizar por escrito una ventana de prueba con datasets no comerciales para:
paridad multi-mall, benchmark con/sin trigger y dos workers con recuperación.
Hasta entonces, mantener PR #299 en borrador y Sprint 2 limitado a Mall Demo.

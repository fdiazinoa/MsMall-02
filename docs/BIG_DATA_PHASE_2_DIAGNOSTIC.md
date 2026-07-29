# Big Data — Fase 2: Diagnóstico 360°

## Objetivo

La Fase 2 convierte una anomalía del mall en un diagnóstico verificable por
local. No sustituye al Dashboard BI ni consulta ventas crudas.

Desde la ficha de anomalía, cada local contribuyente abre una vista con:

- venta observada y referencia histórica por día de semana;
- contribución a la variación;
- comparación contra locales homologados de la misma categoría;
- evolución diaria y cobertura del período;
- archivos y logs de importación relacionados;
- conclusión determinística, confianza y siguiente acción.

## Clasificaciones

- `COMMERCIAL_MOVEMENT`: señal comparable sin fallos de datos relacionados.
- `IMPORT_ISSUE`: la evidencia apunta a falta o degradación de datos.
- `MIXED`: existe señal comercial junto con cobertura o importación dudosa.
- `INSUFFICIENT_DATA`: no existe historia o muestra comparable suficiente.

La clasificación no afirma causalidad absoluta. Las importaciones se vinculan
por fecha incluida en el nombre del archivo o por proximidad de procesamiento.
La interfaz presenta explícitamente la fuerza de esa relación.

La comparación usa la categoría homologada como fuente oficial. Mientras un
mall no tenga taxonomía configurada, utiliza provisionalmente el `rubro` del
local y lo identifica como referencia Legacy; no mezcla locales de otros malls.

## Rendimiento y aislamiento

El endpoint
`GET /api/v1/big-data/intelligence/phase-two/stores/{local_id}`:

- autentica, valida acceso al mall y requiere `BIG_DATA_CORE`;
- limita el diagnóstico a 90 días;
- consulta agregados diarios, nunca `ventas`;
- limita locales del mall a 500 y pares de categoría a 200;
- limita agregados comparables a 10,000 y logs a 100;
- selecciona únicamente columnas necesarias.

No requiere migración SQL: reutiliza `big_data_daily_aggregates`,
`local_commercial_classifications`, `commercial_taxonomy` y `logs_carga`.

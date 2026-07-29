# Big Data — Fase 3A: Predicción explicable

## Objetivo

La Fase 3A proyecta la venta neta del mall para los próximos 7, 30 y 90 días.
No sustituye Dashboard BI, no consulta `ventas` y no afirma resultados
garantizados. Convierte los patrones de Fase 1 y el calendario comercial en un
pronóstico verificable.

## Contrato

`GET /api/v1/big-data/intelligence/phase-three-a/prediction`

Parámetros:

- `mall_id`
- `start_date`: inicio del historial solicitado;
- `end_date`: fecha de corte, limitada por el servidor a la fecha actual.

Seguridad:

- usuario autenticado;
- acceso comprobado al mall;
- licencia `BIG_DATA_CORE`;
- capacidad `BIG_DATA_FORECAST`.

La respuesta contiene:

- horizontes acumulados de 7, 30 y 90 días;
- venta esperada, límite inferior y superior;
- trayectoria diaria;
- confianza, cobertura y razones que la limitan;
- patrón base por día de semana;
- tendencia reciente;
- feriados y eventos futuros conocidos;
- ajustes históricos aprendidos por tipo de evento.

## Metodología

1. Consolida exclusivamente agregados diarios `grain = mall`.
2. Excluye filas posteriores a la fecha de corte, aunque existan por un error de
   origen.
3. Calcula una mediana robusta por día de semana.
4. Excluye feriados y eventos conocidos de esa referencia.
5. Calcula una tendencia de 28 días y la limita a ±20% para evitar
   extrapolaciones descontroladas.
6. Aprende el efecto de un tipo de evento o de los feriados únicamente cuando
   existen al menos dos observaciones históricas comparables.
7. Produce un intervalo explicable del 80% a partir de los residuos históricos.

Si existen menos de 28 días con datos, devuelve `INSUFFICIENT_DATA` y no emite
una cifra.

## Rendimiento

- máximo 500 filas históricas;
- máximo 500 eventos de calendario;
- selección explícita de columnas;
- filtros por `mall_id`, `grain` y rango de fechas;
- cero consultas a ventas crudas;
- una consulta de agregados, una de configuración del mall y una de calendario.

El plan productivo validado para 365 días utiliza
`idx_big_data_daily_mall_date` y ejecuta la lectura en aproximadamente 0.6 ms.
No se requiere un índice nuevo.

## Base de datos

No requiere migración SQL. Reutiliza:

- `big_data_daily_aggregates`;
- `big_data_calendar_events`;
- `mall_feature_flags`;
- `malls`.

La Fase 3B sí deberá persistir escenarios y planes de acción en entidades
separadas; esa persistencia queda fuera del alcance de 3A.

# Big Data — Fase 3B: escenarios y planes de acción

## Objetivo

Fase 3B convierte la predicción explicable de Fase 3A en una herramienta de
planificación. Permite responder preguntas del tipo:

- ¿Qué rango de venta podríamos esperar durante una promoción?
- ¿Cuál sería el impacto potencial de una actividad del mall o una venta de
  pasillo?
- ¿Qué acciones, responsables y fechas deben acompañar la decisión?

El resultado es una comparación contra la predicción base. No representa una
relación causal ni una garantía comercial.

## Flujo funcional

1. El usuario selecciona tipo, fechas y un supuesto de impacto porcentual.
2. El backend recalcula la predicción Fase 3A con el corte seleccionado.
3. El simulador aplica el supuesto únicamente a los días afectados.
4. Se muestran base, escenario, impacto incremental, rango y confianza.
5. Un administrador o usuario IT puede guardar el resultado como borrador con
   un plan de acciones.
6. El escenario avanza por el flujo:
   `DRAFT → APPROVED → ACTIVE → COMPLETED`.
7. Un escenario abierto también puede pasar a `CANCELLED`.

## Contratos API

Todos los contratos requieren usuario autenticado, acceso al mall,
`BIG_DATA_CORE` y `BIG_DATA_FORECAST`.

- `POST /api/v1/big-data/intelligence/phase-three-b/simulate`
- `GET /api/v1/big-data/intelligence/phase-three-b/scenarios`
- `POST /api/v1/big-data/intelligence/phase-three-b/scenarios`
- `PATCH /api/v1/big-data/intelligence/phase-three-b/scenarios/{id}/status`
- `PATCH /api/v1/big-data/intelligence/phase-three-b/actions/{id}/status`

Simular y consultar requieren acceso al mall. Guardar o modificar el flujo
requiere rol administrador o IT.

## Persistencia y seguridad

La migración
`supabase/migrations/20260729190139_big_data_phase_3b_scenarios.sql` crea:

- `big_data_scenarios`
- `big_data_scenario_actions`

Las tablas:

- están aisladas por `mall_id`;
- aplican una llave foránea compuesta para impedir acciones asociadas a un
  escenario de otro mall;
- tienen RLS habilitado y forzado;
- revocan acceso directo a `anon` y `authenticated`;
- conceden privilegios explícitos únicamente a `service_role`;
- se consumen desde FastAPI después de validar usuario, mall, licencia y rol.

La migración es requerida antes de desplegar el backend de Fase 3B. No modifica
`ventas`, importadores, agregados ni funciones existentes.

## Límites del modelo

- Solo se admiten fechas dentro de los próximos 90 días de Fase 3A.
- El supuesto permitido está entre -60% y +80%.
- La referencia histórica se presenta cuando existen observaciones comparables,
  pero nunca reemplaza silenciosamente el supuesto indicado por el usuario.
- Si la predicción base ya incluye un feriado o evento registrado en las fechas
  simuladas, se advierte el riesgo de contar el mismo efecto dos veces.
- La confianza proviene de la calidad de la predicción base.
- El escenario guarda un snapshot; cambios posteriores en ventas o calendario no
  reescriben automáticamente decisiones ya documentadas.

## Orden de despliegue

1. Aplicar y verificar la migración SQL.
2. Desplegar el backend Railway.
3. Verificar simulación y persistencia con un mall de prueba.
4. Desplegar el frontend.
5. Confirmar que escenarios, acciones y cambios de estado permanecen aislados por
   mall.

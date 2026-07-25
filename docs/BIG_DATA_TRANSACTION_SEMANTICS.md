# Semántica de ventas y notas de crédito — Big Data

Fecha de decisión: 2026-07-24

## Decisión comercial

Todo registro de `ventas` con importe neto negativo representa una **nota de
crédito**. Las notas de crédito rebajan las ventas del período, del mall, del
local y de la categoría a los que pertenezca el registro.

La fórmula oficial de venta neta es:

```text
ventas_netas = sum(total_neto)
```

Por lo tanto, las filas positivas incrementan la venta neta y las filas
negativas la reducen. La misma regla se aplica a `total_bruto` e
`total_impuestos` cuando los importadores los informan en negativo.

## Conteo y promedio visibles

La unidad de conteo de Big Data sigue siendo una fila de `ventas` y se expone
en interfaz como **Registros de venta**. No se presenta como una transacción
comercial certificada.

```text
registros_de_venta = count(*)
promedio_por_registro = sum(total_neto) / count(*)
```

Una nota de crédito cuenta como registro y reduce el numerador del promedio.
No se cambia `transaction_count` hasta que exista una regla comercial distinta
para agrupar comprobantes o excluir/anular documentos.

## Agregados y anomalías

`refresh_big_data_aggregates` ya utiliza `sum(total_neto)`,
`sum(total_bruto)` y `sum(total_impuestos)`; por ello los agregados diarios y
mensuales incluyen correctamente las notas de crédito sin reconstrucción ni
migración adicional.

Una nota de crédito no implica por sí sola una caída comercial. Si su volumen
es atípico, el motor genera `ATYPICAL_NEGATIVE` con semántica `CREDIT_NOTE` y
explica que la reducción corresponde a notas de crédito, no a una conclusión
causal sobre la demanda.

## Evidencia consultada

Consulta productiva de solo lectura ejecutada el 2026-07-24:

| Medida | Resultado |
| --- | ---: |
| Filas en `ventas` | 1,792,670 |
| Filas negativas / notas de crédito | 13,132 |
| Venta neta positiva | $12,246,434,426.67 |
| Notas de crédito netas | -$68,547,680.93 |
| Venta neta después de notas de crédito | $12,177,886,745.74 |

Esta decisión elimina la ambigüedad de los valores negativos. La certificación
de transacciones comerciales continúa limitada al conteo de registros hasta
que el negocio defina una semántica adicional de comprobante/ticket.

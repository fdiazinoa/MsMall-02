# Importador API Bundaberg / Ágora

## Objetivo

Extraer las ventas del TPV de Bundaberg mediante HTTP y cargarlas en `ventas` sin mezclar malls o locales. El importador funciona en ejecución manual y automática usando el worker normal de importaciones.

## Contrato recibido

- Método: `GET`.
- Endpoint vigente confirmado el 5 de agosto de 2026: `https://sibs2.com/api_agora_inv/`.
- TPV recibido: `8906`.
- Una fecha: `idTpv`, `fecha` y `apiKey`.
- Rango: `idTpv`, `fechaInicio`, `fechaFin` y `apiKey`.
- Respuesta: objeto JSON con una lista `ventas`.

La captura antigua muestra `https://sibs2.com/api_facturacion/api_agora_bundaberg.php`, pero esa ruta respondió HTTP 404 durante la verificación del 5 de agosto de 2026. La ruta del TXT respondió HTTP 401 sin credencial, confirmando que el recurso existe y exige autenticación. El endpoint permanece editable para que un cambio futuro del proveedor no requiera modificar código.

## Mapeo a MsMall

| Bundaberg | MsMall |
| --- | --- |
| `numserie` | `factura_no` |
| `ncf` | `comprobante` |
| `fecha` | `fecha` |
| `hora` | `hora_transaccion` |
| `totalbruto` | `total_bruto` |
| `totalimpuestos` | `total_impuestos` |
| `totalneto` | `total_neto` |

Si `numserie` no está presente se usa `ncf`; como último recurso se genera `BUNDABERG-{idTpv}-{id_transaccion}`.
Los tres totales monetarios se multiplican por `tasa` y se redondean a dos decimales. Si `tasa` no está presente, es cero o no es válida, se usa `1` para conservar los importes recibidos.

## Configuración en MsMall

1. Abrir **Importación FTP > Nuevo importador** y elegir el local correcto.
2. Seleccionar **API REST** y luego **Bundaberg / Ágora**.
3. Confirmar el endpoint y el ID TPV.
4. Pegar la API key en el campo secreto. No debe guardarse en código, documentación ni capturas nuevas.
5. Seleccionar el período y la frecuencia.
6. Probar la conexión, guardar y ejecutar una importación manual antes de activar el horario automático.

## Operación y seguridad

- Cada fila lleva el `mall_id` y `local_id` de la configuración seleccionada.
- Los duplicados se omiten por `(local_id, fecha, factura_no)`.
- Para Bundaberg, una venta existente con la misma `(local_id, fecha, factura_no)` conserva su identificador y actualiza comprobante, hora y totales con la respuesta más reciente del API.
- Los resultados se registran en el monitor con canal `API` y proveedor `bundaberg`.
- La API key no se devuelve al navegador cuando se listan configuraciones. Un campo secreto vacío al editar conserva la clave existente.
- Los errores se sanitizan antes de escribirse en logs.

## Pendiente antes de activar producción

La API key completa no está visible en los adjuntos. Debe obtenerse por un canal seguro y pegarse directamente en la configuración del local. También debe confirmarse cuál local de MsMall corresponde al TPV `8906`.

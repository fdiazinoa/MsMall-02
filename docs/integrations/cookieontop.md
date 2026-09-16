# CookieOnTop / Citrus

En Importación Automatizada, seleccionar API REST → CookieOnTop / Citrus.
Endpoint: `https://api.citrus.com.do/cookieontop/ventas`. Guardar el token proporcionado por Citrus en el campo de credencial; no requiere usuario ni renovación automática. No incluirlo en constantes, repositorio o URL.

ID TPV es opcional: vacío incluye todas las tiendas autorizadas por el token. Usar esta opción únicamente cuando correspondan al local seleccionado. Para GEI-COOKIEONTOP en Santiago Center, el cliente confirmó que el token corresponde a ese local.

El período predeterminado es el día anterior en America/Santo_Domingo. Se admiten los períodos del selector y rangos de hasta 366 días. Las consultas de un día envían `fecha`; los rangos envían `FechaDesde` y `FechaHasta`, verificados con el servicio real. El ejemplo `fechaInicio/fechaFin` del PDF contradice su tabla de parámetros y no se utiliza.

Cada factura se guarda con `factura_no=COOKIEONTOP-{id_transaccion}`, NCF en `comprobante`, hora y los tres totales convertidos a DOP usando `tasa`. `numserie` identifica al cliente y no se usa como factura. Se aceptan las variantes de mayúsculas del PDF y de la respuesta real.

La inserción usa la restricción única existente `(local_id, fecha, factura_no)` con conflictos omitidos, incluso en ejecuciones concurrentes. Reprocesar no actualiza ventas previas. Las consultas se validan completas antes de insertar: un registro inválido, una transacción contradictoria o una fecha fuera del rango falla explícitamente. La carga se divide en lotes de 500; si falla un lote posterior, se registra el progreso como parcial y es seguro reprocesar.

El límite explícito de 10000 registros del proveedor divide automáticamente el rango. Si un solo día excede el límite, se requiere filtrar por TPV. Se aceptan arreglos vacíos y 404 que indiquen explícitamente ausencia de ventas. Un 404 ambiguo o de TPV, 401, 429 o 500 se registra como error. Los errores del proveedor no exponen cuerpos ni credenciales. No se siguen redirecciones con el Bearer token.

## Verificación inicial, 16 de septiembre de 2026

- API y base de datos: 30 facturas del 15/09/2026.
- Bruto: RD$16,631.39; impuestos: RD$2,993.61; neto: RD$19,625.00.
- Reprocesamiento: 0 inserciones, 30 duplicados omitidos.
- Configuración guardada en modo manual; período predeterminado: día anterior.
- Activar la frecuencia diaria desde la aplicación cuando el API y worker tengan desplegado este conector. No requiere migración de esquema.

Pruebas: `python3 -m pytest tests/test_cookieontop_api_import.py tests/test_studio_g_api_import.py tests/test_bundaberg_api_import.py tests/test_generic_webservice_import.py tests/test_bundaberg_api_ui.py tests/test_frontend_import_config_reactivation.py -q` y `npm run build`.

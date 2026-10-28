# Ventas Plazas: EGO y Lattliv, Megacentro

Conector basado en Instructivo.pdf. Crear una conexión API independiente para cada local en Importaciones y seleccionar **Ventas Plazas / EGO / Lattliv**.

- Endpoint: `https://egord.ddns.net/api/Ventas/ConsultarVentasPlazas`.
- Usuario/equipo: `X-Equipment-Id` autorizado por el proveedor.
- Contraseña: JWT sin el prefijo `Bearer`, guardado mediante el mecanismo de secretos existente.
- ID TPV: código asignado por el proveedor al local; `LWAT` aparece como ejemplo en el PDF y no se configura automáticamente.
- Periodo: día anterior, mes actual o rango personalizado según la operación.

El worker realiza GET con `idTpv`, `fechaDesde` y `fechaHasta` en formato `yyyyMMdd`. Envía Authorization Bearer, X-Equipment-Id y Content-Type application/json. No llama al endpoint de autorización de Studio G.

Mapea FECHA, HORA, NCF, ID_TRANSACCION, TOTALBRUTO, TOTALIMPUESTOS y TOTALNETO. Usa NCF como factura; si falta, usa `PLAZAS-{idTpv}-{ID_TRANSACCION}`. NUMSERIE es fijo según el contrato y no se usa como identidad. TASA es un indicador impositivo y no multiplica importes. Conserva el mecanismo existente de detección de duplicados por local.

El PDF no muestra el contenedor de respuesta. Se aceptan una lista JSON y un objeto con lista `ventas`; otras formas fallan explícitamente. Confirmar el formato real durante la prueba con credenciales. Los errores HTTP, incluidos 401 y 403, producen una carga fallida.

## Activación pendiente

Confirmar el local exacto de Megacentro para cada conexión, sus códigos TPV y equipos autorizados. Introducir los JWT en los campos protegidos y ejecutar prueba de conexión y vista previa antes de habilitar el horario automático. El proveedor debe indicar vigencia y renovación del JWT: el PDF no documenta un endpoint para renovarlo automáticamente. Un token vencido requiere reemplazar la credencial guardada.

Esta implementación no despliega ni habilita conexiones de producción y no modifica POS ni esquema de base de datos.

Validación: pruebas de contrato con HTTP simulado, validación de credenciales, respuestas inválidas, selección de proveedor y configuración de vista previa; regresión de conectores existentes y build web. La prueba real contra el proveedor requiere las credenciales anteriores.

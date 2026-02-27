# Guia de configuracion: MsMall + MsExportador (tokens y webservice)

## 1) Objetivo
Esta guia define como habilitar y operar la integracion segura entre `MsMall` y `MsExportador` usando:
- configuracion por local del canal ERP Webservice,
- service accounts,
- tokens `exporter`,
- y endpoints dedicados de ingesta.

## 2) Arquitectura (resumen)
- `MsMall` expone endpoints de seguridad y de ingesta para exporter.
- `MsExportador` autentica con `client_id/client_secret` (service account) para obtener tokens.
- `MsExportador` envia ventas solo para su `mall_id + local_id`.
- `MsMall` valida:
  - que el token sea `exporter`,
  - que `mall_id/local_id` del payload coincida con claims del token,
  - y reglas por local en ERP Webservice (enabled, granularity permitida, etc).

## 3) Configuracion en MsMall (backend)

### 3.1 Variables de entorno obligatorias
Configurar en el backend de MsMall:
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (preferido) o `SUPABASE_KEY`
- `MSMALL_TOKEN_JWT_SECRET`

Recomendadas:
- `MSMALL_TOKEN_JWT_ALG` (default: `HS256`)
- `TOKEN_APP_ACCESS_MINUTES`
- `TOKEN_APP_REFRESH_DAYS`
- `TOKEN_EXPORTER_ACCESS_HOURS`
- `TOKEN_EXPORTER_REFRESH_DAYS`

## 3.2 Migraciones SQL requeridas
Ejecutar en Supabase (en este orden):
1. `20260225_auth_tokens_core.sql`
2. `20260226_auth_tokens_service_account_name.sql`
3. `20260226_exporter_sales_ingest.sql`
4. `20260226_exporter_webservice_configs.sql`

## 3.3 Servicios/rutas que deben estar activos
- Router de token auth (`create_token_auth_router`) cargado en FastAPI.
- Endpoints de seguridad UI (wrappers):
  - `GET/POST /api/v1/security/service-accounts`
  - `GET/POST /api/v1/security/tokens`
  - `GET /api/v1/security/token-audit`
  - `GET/PUT /api/v1/security/exporter/configs...`
- Endpoints dedicados para exporter:
  - `POST /auth/token`
  - `POST /auth/refresh`
  - `POST /api/v1/exporter/sync/ingest`
  - `POST /api/v1/remote/execute-manual/exporter` (uso puntual/manual)

## 3.4 Roles y accesos
- Usuario operador en MsMall Web debe tener rol `ADMIN` o `IT/TIC`.
- El usuario debe tener asignacion al mall en `usuarios_malls`.

## 4) Configuracion en MsMall (UI)

## 4.1 Configurar ERP Webservice por local
Ruta: `Import Manager > ERP Webservice (MsExportador)`

Por cada local:
1. Seleccionar local.
2. Definir:
   - `Canal habilitado` (on/off)
   - `Granularidad por defecto` (`transaction` o `daily`)
   - `Permitir transaccion`
   - `Permitir resumen diario`
   - `Validacion estricta`
   - `Notas`
3. Guardar configuracion.

Notas:
- Esta configuracion es independiente del canal FTP/SFTP.
- El estado de la derecha (`SIN CONFIG`, `HABILITADO`, `DESHABILITADO`) resume cada local.

## 4.2 Crear Service Account para MsExportador
Ruta: `Seguridad > Service Accounts y Tokens > Crear Service Account`

Recomendado:
- 1 service account por local (`mall_id + local_id`).
- Scopes minimos: `export:write` y `mapping:read`.

Guardar de forma segura (one-time reveal):
- `client_id`
- `client_secret`

## 4.3 Emitir token exporter (opcional desde UI)
Ruta: `Seguridad > Service Accounts y Tokens > Crear Token`

- `token_type = exporter`
- `mall_id` y `local_id` del local correcto
- scopes segun necesidad (minimo `export:write`)

Nota: en operacion automatizada, lo normal es que MsExportador pida token via `/auth/token` usando `client_id/client_secret`.

## 5) Configuracion en MsExportador

## 5.1 Datos minimos por local
MsExportador debe tener por local:
- `base_url` de MsMall API (ej: `https://<tu-backend>/api/v1`)
- `mall_id`
- `local_id`
- `client_id`
- `client_secret`

## 5.2 Flujo recomendado de autenticacion
1. Solicitar token:

```bash
curl -X POST "https://<backend>/auth/token" \
  -H "Content-Type: application/json" \
  -d '{
    "token_type": "exporter",
    "client_id": "<client_id>",
    "client_secret": "<client_secret>"
  }'
```

2. Respuesta esperada: `access_token`, `refresh_token`, expiracion.
3. Guardar `refresh_token` de forma segura y rotarlo siempre.
4. Renovar con `/auth/refresh` antes de expirar (por ejemplo al 70-80% de vida util).

## 5.3 Envio de ventas (ingesta)
Endpoint:
- `POST /api/v1/exporter/sync/ingest`

Headers:
- `Authorization: Bearer <access_token>`

Payload base:
```json
{
  "mall_id": "<mall_id>",
  "local_id": "<local_id>",
  "rows": [...],
  "meta": {
    "granularity": "transaction"
  }
}
```

Reglas de validacion:
- Si `granularity=transaction`: requiere al menos `documento_numero` (o alias), `fecha_venta`, `hora_venta`, `total_bruto`, `total_impuesto`, `total_neto`.
- Si `granularity=daily`: requiere `fecha_venta`, `total_bruto`, `total_impuesto`, `total_neto` y `resumen_id` si no hay `documento_numero`.
- `mall_id/local_id` del payload debe coincidir con el token exporter.

## 5.4 Politica de reintentos sugerida
- `401`: refrescar token y reintentar una vez.
- `403`: no reintentar; revisar scopes o mall/local.
- `409`: canal deshabilitado en MsMall para ese local.
- `422`: payload invalido o granularidad no permitida.
- `5xx`: backoff exponencial + alerta.

## 6) Checklist de puesta en marcha
1. Migraciones SQL aplicadas.
2. Variables de entorno cargadas en MsMall.
3. Usuario ADMIN/IT asignado al mall.
4. ERP Webservice configurado y guardado por local.
5. Service account creado por local.
6. MsExportador configurado con `client_id/client_secret` correctos.
7. Token emitido y prueba de ingest (`rows` de prueba).
8. Verificar registros en `exporter_sales_ingest`.

## 7) Operacion y seguridad
- Rotar `client_secret` periodicamente.
- Revocar tokens por local ante incidente:
  - `POST /auth/revoke/local` o via UI.
- Revocar por mall ante incidente mayor:
  - `POST /auth/revoke/mall` o via UI.
- Monitorear `token_audit_log` y errores de ingesta.

## 8) Troubleshooting rapido
- `mall_id/local_id del payload no coincide con el token`:
  - MsExportador esta enviando un local distinto al token emitido.
- `Webservice exporter deshabilitado para este local`:
  - Activar `Canal habilitado` en ERP Webservice.
- `Granularity 'transaction' no permitido...`:
  - Ajustar flags `Permitir transaccion/daily` en MsMall.
- `Local no encontrado...` o `codigo_interno` faltante:
  - Validar local en tabla `locales` y su `codigo_interno`.
- `Supabase no configurado para token auth`:
  - Revisar `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY` en backend MsMall.

## 9) Endpoints clave (referencia)
- Emision/refresh/revocacion:
  - `POST /auth/token`
  - `POST /auth/refresh`
  - `POST /auth/revoke`
  - `POST /auth/revoke/local`
  - `POST /auth/revoke/mall`
- Exporter:
  - `POST /api/v1/exporter/sync/ingest`
  - `GET /api/v1/security/exporter/configs`
  - `PUT /api/v1/security/exporter/configs/{local_id}`
- Admin seguridad UI:
  - `GET/POST /api/v1/security/service-accounts`
  - `GET/POST /api/v1/security/tokens`
  - `GET /api/v1/security/token-audit`


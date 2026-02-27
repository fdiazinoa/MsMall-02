# Token Auth Central (MsMall + MsExportador)

## Variables de entorno
- `MSMALL_TOKEN_JWT_SECRET` (obligatorio en prod)
- `MSMALL_TOKEN_JWT_ALG` (default `HS256`, nunca `none`)
- `TOKEN_APP_ACCESS_MINUTES` (default `30`)
- `TOKEN_APP_REFRESH_DAYS` (default `14`)
- `TOKEN_EXPORTER_ACCESS_HOURS` (default `12`)
- `TOKEN_EXPORTER_REFRESH_DAYS` (default `90`)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (preferido) o `SUPABASE_KEY`

## Endpoints principales
- `POST /auth/token` emite `access_token` + `refresh_token`
- `POST /auth/refresh` rota refresh (invalida el anterior)
- `POST /auth/revoke` revoca token actual o por `token_id`/`jti`
- `POST /auth/revoke/local` revoca tokens por `mall_id + local_id`
- `POST /auth/revoke/mall` revoca tokens por `mall_id`
- `GET /tokens` listado (requiere `tokens:manage`)
- `POST /tokens` creación manual admin (one-time reveal)
- `PATCH /tokens/:id/status` activa/desactiva
- `POST /tokens/:id/regenerate` regenera (revoca anterior)
- `POST /service-accounts` crea credenciales exporter (one-time reveal `client_secret`)
- `GET /service-accounts` lista service accounts exporter
- `PATCH /service-accounts/:id/status` activa/desactiva
- `POST /service-accounts/:id/regenerate` regenera `client_secret` (one-time reveal y revoca tokens asociados)
- `POST /service-accounts/:id/revoke-tokens` revoca tokens asociados al service account
- `GET /token-audit` auditoría básica de uso (eventos emitidos/refreshed/revoked/used/failed)
- `POST /api/v1/remote/execute-manual/exporter` ejecuta importación manual real usando token exporter (valida `config_id` contra `mall_id/local_id` del token)

## UI Admin (MsMall Web)
- Pantalla: `Seguridad > Service Accounts y Tokens`
- Requiere sesión de MsMall Web con rol `ADMIN` (backend permite `IT` también para operaciones de seguridad).
- La UI usa endpoints admin de compatibilidad con sesión Supabase:
  - `GET/POST /api/v1/security/service-accounts`
  - `PATCH /api/v1/security/service-accounts/:id/status`
  - `POST /api/v1/security/service-accounts/:id/regenerate`
  - `POST /api/v1/security/service-accounts/:id/revoke-tokens`
  - `GET/POST /api/v1/security/tokens`
  - `PATCH /api/v1/security/tokens/:id/status`
  - `POST /api/v1/security/tokens/:id/regenerate`
  - `POST /api/v1/security/tokens/revoke`
  - `POST /api/v1/security/tokens/revoke/local`
  - `POST /api/v1/security/tokens/revoke/mall`
  - `GET /api/v1/security/token-audit`
- One-time reveal:
  - `client_secret` solo se muestra al crear/regenerar service account.
  - `access_token` / `refresh_token` solo se muestran al crear/regenerar token.

## Migraciones adicionales UI
- Ejecutar también `20260226_auth_tokens_service_account_name.sql` para soportar nombre legible de service accounts en la UI admin.

## Rutas recomendadas por cliente
- `MsMall Web` (usuario + token `app`): usar rutas actuales de usuario como `/api/v1/ingesta` y `/api/v1/remote/execute-manual`.
- `MsExportador` (servicio local + token `exporter`): usar rutas dedicadas `/api/v1/exporter/sync/ingest` y `/api/v1/remote/execute-manual/exporter`.
- `MsExportador` no debe usar `/api/v1/ingesta` (esa ruta mantiene el flujo de usuario de MsMall Web).

## Integración MsExportador (recomendado)
1. Provisionar `service-account` por local (`mall_id` + `local_id`).
2. Pedir token exporter con `client_id/client_secret` en `/auth/token`.
3. Usar `Bearer access_token` en rutas dedicadas de exporter (`/api/v1/exporter/sync/ingest`, `/api/v1/remote/execute-manual/exporter`).
4. Renovar con `/auth/refresh` cuando falte ~20% de vida del access token.
5. Persistir solo `refresh_token` y rotarlo siempre (reemplazar el anterior).

## Guia operativa completa
- Ver `GUIA_CONFIG_MSEXPORTADOR_MSMALL_TOKENS_WEBSERVICE.md` para setup paso a paso (MsMall + MsExportador), checklist de habilitacion y troubleshooting.

## Reglas de seguridad implementadas
- Claims: `mall_id`, `local_id` (exporter), `token_type`, `scope`, `jti`, `iat`, `exp`
- Refresh token guardado con hash (no plaintext)
- JWT firmado (`HS256` por defecto)
- Revocación individual/local/mall
- Auditoría básica (`token_audit_log`)
- Rate limit básico in-memory en `/auth/token`, `/auth/refresh`, `/auth/revoke*`
- No se loguean tokens completos
- Validación estricta de `mall_id` + `local_id` en endpoint exporter de ejemplo

## Errores comunes / HTTP codes
- `400` payload inválido / faltan credenciales / `local_id` faltante en exporter
- `401` token inválido/expirado/revocado o refresh inválido
- `403` scope insuficiente o `mall_id/local_id` no coincide con token exporter
- `404` token no encontrado
- `429` rate limit
- `500` configuración faltante (JWT/Supabase)

## Ejemplos de errores esperados (MsExportador)
- `401` `{"detail":"Bearer token requerido"}`: falta header `Authorization: Bearer ...`
- `401` `{"detail":"Access token expirado"}` o `{"detail":"Access token inválido"}`: token expirado/incorrecto
- `403` `{"detail":"mall_id/local_id del payload no coincide con el token"}`: intento de enviar data de otro local
- `429` `{"detail":"Rate limit exceeded"}`: demasiados intentos en `/auth/token`, `/auth/refresh` o `/auth/revoke*`

## Ejemplos
- Ver `examples/token_auth_flow.http`

## Notas de compatibilidad
- No reemplaza el auth actual de MsMall Web; agrega backend central de tokens.
- `token_type=app` intenta reutilizar login existente de Supabase (`sign_in_with_password`).
- Si el flujo real de usuarios difiere, ajustar integración en `routers/token_auth.py` (`authenticate_app_user`).
- La UI admin de seguridad usa wrappers `/api/v1/security/*` para operar con la sesión actual de MsMall Web sin pedir credenciales adicionales.

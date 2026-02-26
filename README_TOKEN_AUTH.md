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
- `POST /api/v1/remote/execute-manual/exporter` ejecuta importación manual real usando token exporter (valida `config_id` contra `mall_id/local_id` del token)

## Integración MsExportador (recomendado)
1. Provisionar `service-account` por local (`mall_id` + `local_id`).
2. Pedir token exporter con `client_id/client_secret` en `/auth/token`.
3. Usar `Bearer access_token` en endpoints de sync/ingesta.
4. Renovar con `/auth/refresh` cuando falte ~20% de vida del access token.
5. Persistir solo `refresh_token` y rotarlo siempre (reemplazar el anterior).

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

## Ejemplos
- Ver `examples/token_auth_flow.http`

## Notas de compatibilidad
- No reemplaza el auth actual de MsMall Web; agrega backend central de tokens.
- `token_type=app` intenta reutilizar login existente de Supabase (`sign_in_with_password`).
- Si el flujo real de usuarios difiere, ajustar integración en `routers/token_auth.py` (`authenticate_app_user`).

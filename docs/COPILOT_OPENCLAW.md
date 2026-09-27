# Copilot MsMall con OpenClaw

## Frontera de seguridad

El navegador nunca se conecta directamente a OpenClaw. El flujo es:

1. El usuario inicia sesión en MsMall con Supabase Auth.
2. El backend valida el JWT, el rol y el acceso al `mall_id` solicitado.
3. El backend consulta Supabase con filtros explícitos por mall y construye un JSON operativo limitado.
4. Solo ese JSON, la pregunta y hasta ocho mensajes recientes se envían al gateway.
5. OpenClaw devuelve texto; no recibe claves de Supabase ni una conexión a la base de datos.
6. Los reportes y borradores de correo siguen siendo generados por MsMall. El envío requiere el botón de confirmación existente.

Las solicitudes al gateway son deliberadamente independientes: no se envía `user` ni `x-openclaw-session-key`. Esto evita que una sesión persistente de OpenClaw mezcle contexto entre usuarios o malls.

## Variables privadas del backend MsMall

Configurar en el servicio Railway que ejecuta `main.py`:

```text
OPENCLAW_GATEWAY_URL=http://clawdbot-railway-template.railway.internal:18790
OPENCLAW_GATEWAY_TOKEN=<token del gateway>
```

MsMall y OpenClaw están en el mismo proyecto Railway, por lo que esta ruta usa la red privada y evita publicar el endpoint del Copilot en Internet. También se admite HTTPS para otros despliegues y HTTP exclusivamente para `localhost` o dominios `*.railway.internal`. El token es una credencial de operador de OpenClaw: no debe llevar prefijo `VITE_`, guardarse en Supabase ni copiarse al frontend.

### Adaptador privado del template Railway

El template `vignesh07/clawdbot-railway-template` protege su wrapper público (`PORT`, normalmente `3000`) con autenticación Basic. No se debe apuntar MsMall a `/openclaw`, porque ese wrapper rechaza el encabezado Bearer antes de que llegue al endpoint OpenAI-compatible.

En el servicio OpenClaw se mantiene un adaptador HTTP mínimo en `0.0.0.0:18790` que:

- solo acepta `POST /v1/chat/completions`;
- reenvía la solicitud a `127.0.0.1:18789`, donde escucha el gateway;
- conserva `Authorization: Bearer ...` para que OpenClaw valide el token;
- se inicia desde `/data/workspace/bootstrap.sh`, por lo que persiste en el volumen y vuelve a levantarse después de un redeploy;
- no tiene dominio público ni se publica mediante Railway Public Networking.

El puerto `18790` es exclusivamente para la red privada de Railway. La interfaz `/setup` continúa protegida por `SETUP_PASSWORD` en el puerto público del wrapper.

## Configuración del gateway

El gateway debe habilitar Chat Completions:

```json5
{
  gateway: {
    http: {
      endpoints: {
        chatCompletions: { enabled: true }
      }
    }
  }
}
```

El modelo que MsMall envía al gateway para OpenClaw 2026.3.8 es `openclaw:msmall`. Debe existir un agente `msmall` dedicado, sin canales de mensajería y con las herramientas sensibles deshabilitadas. No se debe reutilizar el agente principal con perfil `coding`.

El modelo de proveedor configurado dentro de OpenClaw debe estar disponible para la clave instalada. La instalación validada usa `openai/gpt-4o-mini`; comprobarlo con `openclaw models status --agent msmall --probe --probe-provider openai` antes de activar Copilot.

## Activación

En **Administración → Copilot MsMall**:

1. Seleccionar `OpenClaw (gateway privado)`.
2. Mantener el modelo `openclaw:msmall`.
3. Verificar que Gateway y Token aparezcan configurados.
4. Activar Copilot y guardar.

## Prueba mínima

1. Entrar con un usuario que solo tenga acceso a un mall.
2. Preguntar por los locales o las ventas recientes de ese mall.
3. Intentar mencionar por nombre otro mall y confirmar que el backend responda `403` o no entregue sus datos.
4. Preparar un correo y comprobar que no se envía hasta pulsar **Enviar correo**.

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
OPENCLAW_GATEWAY_URL=http://clawdbot-railway-template.railway.internal:3000/openclaw
OPENCLAW_GATEWAY_TOKEN=<token del gateway>
```

MsMall y OpenClaw están en el mismo proyecto Railway, por lo que esta ruta usa la red privada y evita publicar el endpoint del Copilot en Internet. También se admite HTTPS para otros despliegues y HTTP exclusivamente para `localhost` o dominios `*.railway.internal`. El token es una credencial de operador de OpenClaw: no debe llevar prefijo `VITE_`, guardarse en Supabase ni copiarse al frontend.

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

El modelo predeterminado para OpenClaw 2026.3.8 es `openclaw:msmall`. Debe existir un agente `msmall` dedicado, sin canales de mensajería y con las herramientas sensibles deshabilitadas. No se debe reutilizar el agente principal con perfil `coding`.

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

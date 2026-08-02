# Pending Import Monitor

Función programada de Railway para recuperar importaciones remotas que no encontraron archivo durante el ciclo regular.

- Cron en Railway (UTC): `0 0,15,18,21 * * *`
- Horario de República Dominicana: 8pm, 11am, 2pm y 5pm.
- Busca logs exitosos con `archivo = N/A` y el mensaje de archivo nuevo no encontrado.
- Consulta la carpeta real por FTP o SFTP, omite archivos ya importados y solicita al worker procesar el archivo más reciente elegible.
- Registra cada revisión en `connection_runs` y `retry_attempts`.

## Sincronización

El archivo `index.tsx` es la fuente versionada. Para publicar una modificación validada:

```bash
railway functions push -p railway-functions/pending-import-monitor/index.tsx
```

Para verificar que la versión local coincide con Railway:

```bash
railway functions pull -p railway-functions/pending-import-monitor/index.tsx
```

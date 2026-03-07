#!/bin/bash
# Script para iniciar el Worker de Importación Automatizada
# Este proceso se ejecuta en segundo plano y verifica periódicamente si hay importaciones programadas

cd "$(dirname "$0")"

POLL_SECONDS="${WORKER_POLL_SECONDS:-300}"

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Ejecutar el worker en loop infinito
while true; do
    echo "[$(date)] Ejecutando worker de importación..." >> worker.log 2>&1
    python3 worker_importacion.py < /dev/null >> worker.log 2>&1
    echo "[$(date)] Worker terminado. Esperando ${POLL_SECONDS}s..." >> worker.log 2>&1
    sleep "$POLL_SECONDS"
done

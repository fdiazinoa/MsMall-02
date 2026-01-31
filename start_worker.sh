#!/bin/bash
# Script para iniciar el Worker de Importación Automatizada
# Este proceso se ejecuta en segundo plano y verifica cada hora si hay importaciones programadas

cd "$(dirname "$0")"

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Ejecutar el worker en loop infinito (cada hora)
while true; do
    echo "[$(date)] Ejecutando worker de importación..."
    python3 worker_importacion.py
    echo "[$(date)] Worker terminado. Esperando 1 hora..."
    sleep 3600  # Esperar 1 hora (3600 segundos)
done

#!/usr/bin/env bash
# Entrypoint para el servicio Railway dedicado al worker de importacion.

cd "$(dirname "$0")"

export TZ="${TZ:-America/Santo_Domingo}"
export WORKER_TIMEZONE="${WORKER_TIMEZONE:-$TZ}"

# Activar entorno virtual si existe
if [ -d ".venv" ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi

WORKER_POLL_SECONDS="${WORKER_POLL_SECONDS:-300}"

case "$WORKER_POLL_SECONDS" in
    ''|*[!0-9]*)
        echo "[$(date -Is)] WORKER_POLL_SECONDS invalido ('$WORKER_POLL_SECONDS'); usando 300."
        WORKER_POLL_SECONDS=300
        ;;
esac

if [ "$WORKER_POLL_SECONDS" -lt 60 ]; then
    echo "[$(date -Is)] WORKER_POLL_SECONDS menor a 60; usando 60."
    WORKER_POLL_SECONDS=60
fi

shutdown_requested=0
trap 'shutdown_requested=1; echo "[$(date -Is)] Señal recibida; el worker se detendrá al terminar el ciclo actual."' TERM INT

echo "[$(date -Is)] Worker de importacion iniciado. Intervalo=${WORKER_POLL_SECONDS}s TZ=${TZ} WORKER_TIMEZONE=${WORKER_TIMEZONE}"

while [ "$shutdown_requested" -eq 0 ]; do
    echo "[$(date -Is)] Ejecutando ciclo worker_importacion.py"
    python3 -u worker_importacion.py < /dev/null
    exit_code=$?

    if [ "$exit_code" -ne 0 ]; then
        echo "[$(date -Is)] worker_importacion.py terminó con código ${exit_code}; Railway mantendrá vivo el servicio y se reintentará en el próximo ciclo."
    else
        echo "[$(date -Is)] Ciclo worker completado."
    fi

    if [ "$shutdown_requested" -eq 1 ]; then
        break
    fi

    echo "[$(date -Is)] Esperando ${WORKER_POLL_SECONDS}s para el próximo ciclo."
    sleep "$WORKER_POLL_SECONDS" &
    wait $!
done

echo "[$(date -Is)] Worker de importacion detenido."

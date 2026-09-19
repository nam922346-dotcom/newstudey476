#!/bin/bash

source /scripts/02-common.sh

log_message "RUNNING" "07-start-wine-flask.sh"

log_message "INFO" "Waiting for MT5 terminal login (live tick for EURUSDm)..."

_wait_ok=0
for i in $(seq 1 120); do
    if $wine_executable python -c "import MetaTrader5 as mt5; mt5.initialize(); t=mt5.symbol_info_tick('EURUSDm'); mt5.shutdown(); raise SystemExit(0 if t else 1)" >/dev/null 2>&1; then
        log_message "INFO" "MT5 terminal ready (tick OK after ~$((i*5))s)"
        _wait_ok=1
        break
    fi
    sleep 5
done

if [ "$_wait_ok" != "1" ]; then
    log_message "WARN" "Timed out waiting for tick - starting Flask anyway"
fi

log_message "INFO" "Starting Flask server in Wine environment..."
nohup $wine_executable python /app/app.py >> /config/flask.log 2>&1 &

FLASK_PID=$!
sleep 5

if ps -p $FLASK_PID > /dev/null; then
    log_message "INFO" "Flask server started successfully with PID $FLASK_PID."
else
    log_message "ERROR" "Failed to start Flask server in Wine."
    exit 1
fi
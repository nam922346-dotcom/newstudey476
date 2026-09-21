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

# Ensure all strategy symbols are subscribed in MT5's Market Watch. After a
# container restart MT5 forgets the subscription, symbol_info_tick returns
# 404 for those pairs, and the entry algorithm skips them as "market is not
# open". symbol_select(symbol, True) re-subscribes them.
log_message "INFO" "Subscribing strategy symbols in Market Watch..."
$wine_executable python -c "
import MetaTrader5 as mt5
mt5.initialize()
symbols = ['XNGUSDm', 'USOILm', 'XAGUSDm', 'XAUUSDm', 'XAUEURm', 'EURUSDm', 'EURGBPm', 'USDJPYm', 'USDCADm', 'USDCHFm', 'AUDUSDm', 'NZDUSDm']
for s in symbols:
    try:
        mt5.symbol_select(s, True)
    except Exception:
        pass
mt5.shutdown()
" >/dev/null 2>&1 || true
log_message "INFO" "Symbol subscription done."

log_message "INFO" "Starting Flask server in Wine environment..."

# Launch WITHOUT redirecting stdout/stderr to a file: redirecting breaks Wine
# Python sys streams (init_sys_streams: Invalid handle). Plain fork is what
# worked in the base setup.
$wine_executable python /app/app.py &

FLASK_PID=$!
sleep 5

if ps -p $FLASK_PID > /dev/null; then
    log_message "INFO" "Flask server started successfully with PID $FLASK_PID."
else
    log_message "ERROR" "Failed to start Flask server in Wine."
    exit 1
fi
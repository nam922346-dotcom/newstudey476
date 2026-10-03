from app.utils.constants import CRYPTOCURRENCIES, TIMEZONE, MT5Timeframe

# Exness broker symbols carry a trailing "m" (EURUSDm, XAUUSDm, ...).
# BRN is not available on Exness, so it was dropped; NG -> XNGUSDm and WTI -> USOILm.
PAIRS = ['XNGUSDm', 'USOILm', 'XAGUSDm', 'XAUUSDm', 'XAUEURm', 'EURUSDm', 'EURGBPm', 'USDJPYm', 'USDCADm', 'USDCHFm', 'AUDUSDm', 'NZDUSDm']
MAIN_TIMEFRAME = MT5Timeframe.M15

TP_PNL_MULTIPLIER = 0.5
SL_PNL_MULTIPLIER = -0.5
LEVERAGE = 200
DEVIATION = 20
# Raised so high-priced / low-lot pairs (USDJPY, USOIL) produce >= 0.01 lot.
# NOTE: this raises risk-per-trade proportionally (not 0.5%/trade) — verify against
# your account size before live.
CAPITAL_PER_TRADE = 800

TRAILING_STOP_STEPS = [
    {'trigger_risk_multiple': 1.00, 'new_sl_risk_multiple': 0.60},
    {'trigger_risk_multiple': 1.50, 'new_sl_risk_multiple': 1.00},
    {'trigger_risk_multiple': 2.00, 'new_sl_risk_multiple': 1.50},
    {'trigger_risk_multiple': 2.50, 'new_sl_risk_multiple': 2.00},
    {'trigger_risk_multiple': 3.00, 'new_sl_risk_multiple': 2.50},
    {'trigger_risk_multiple': 3.50, 'new_sl_risk_multiple': 3.00},
    {'trigger_risk_multiple': 4.00, 'new_sl_risk_multiple': 3.50},
]

# P6 - so dong mutation (TradeClosePricesMutation) toi da ghi 1 lan moi chu ky
# trailing 15s (batch insert de giam ghi DB).
MAX_TRAILING_MUTATIONS_PER_CYCLE = 5

# ===== P14 — per-stack strategy override (mt52 isolation) =====
# If the stack's working dir env var is set AND the file below exists, its values
# REPLACE the default ones above for THIS stack only. Missing file => defaults stay
# (behaviour identical to today). NEVER read from the other stack's folder.
STRATEGY = 'mean_reversion'   # P14 — strategy name (labels Trade.strategy + logs)

import os as _os

_OVERRIDE_PATH = _os.environ.get(
    "STRATEGY_OVERRIDE",
    "/config/mt52_strategy.py",     # used by mt52 container only
)
if _os.path.exists(_OVERRIDE_PATH):
    _ns = {}
    with open(_OVERRIDE_PATH, "r", encoding="utf-8") as _fh:
        exec(compile(_fh.read(), _OVERRIDE_PATH, "exec"), _ns)
    for _k, _v in _ns.items():
        if not _k.startswith("_"):
            globals()[_k] = _v
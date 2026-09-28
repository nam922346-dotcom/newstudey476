# backend/django/app/risk/pre_flight.py — P4 pre-flight gate (DRY-RUN aware)

import logging
import time
from datetime import datetime

from app.utils.api.account import get_account, get_equity
from app.utils.constants import rule, TIMEZONE

logger = logging.getLogger(__name__)

_last_entry_at = 0.0  # cooldown state (module-level, worker context)


def pre_flight_checks(symbol=None):
    """Chay 4 nhom kiem tra: equity hop le / cooldown / free_margin>=X% / blackout.

    Tra {'ok': bool, 'checks': {...}, 'reasons': [...]}.
    O P4 mang tinh quan sat: entry KHONG bi chan (dry-run). P5 se enforce ok=False -> skip.
    """
    checks, reasons = {}, []

    # 1) equity hop le
    equity = get_equity()
    equity_ok = equity is not None and equity > 0
    checks['equity_ok'], checks['equity'] = equity_ok, equity
    if not equity_ok:
        reasons.append(f"equity invalid/unavailable: {equity}")

    # 2) free_margin >= X% equity
    free_pct = float(rule('MIN_FREE_MARGIN_PCT', 0.20))
    account = get_account()
    free_margin = None
    if account:
        _fm = account.get('margin_free') if account.get('margin_free') is not None else account.get('free_margin')
        if _fm is not None:
            free_margin = float(_fm)
    margin_ok = equity_ok and free_margin is not None and free_margin >= equity * free_pct
    checks['free_margin_ok'], checks['free_margin'] = margin_ok, free_margin
    if not margin_ok:
        reasons.append(f"free_margin {free_margin} < {free_pct * 100:.0f}% equity {equity}")

    # 3) cooldown giua 2 lenh
    cooldown_seconds = float(rule('COOLDOWN_SECONDS', 60))
    now = time.time()
    elapsed = (now - _last_entry_at) if _last_entry_at else float('inf')
    cooldown_ok = elapsed >= cooldown_seconds
    checks['cooldown_ok'] = cooldown_ok
    checks['cooldown_remaining'] = max(0.0, cooldown_seconds - elapsed)
    if not cooldown_ok:
        reasons.append(f"cooldown active ({checks['cooldown_remaining']:.0f}s left)")

    # 4) khong trong blackout
    blackout_ok, blackout_hit = _blackout_check()
    checks['blackout_ok'], checks['blackout_window'] = blackout_ok, blackout_hit
    if not blackout_ok:
        reasons.append(f"blackout window {blackout_hit}")

    return {
        'ok': all([equity_ok, margin_ok, cooldown_ok, blackout_ok]),
        'checks': checks,
        'reasons': reasons,
    }


def _blackout_check():
    windows = rule('BLACKOUT_WINDOWS', []) or []
    if not windows:
        return True, None
    now = datetime.now(TIMEZONE)
    wd = now.weekday()
    cur = now.strftime('%H:%M')
    for w in windows:
        if w.get('weekday') != wd:
            continue
        start, end = w.get('start', '00:00'), w.get('end', '00:00')
        if start <= cur < end:
            return False, w
    return True, None


def enter_pre_flight_gate(symbol=None):
    """Cong entry tong hop 4 kiem tra. P4: log ket qua, luon tra True (khong chan)."""
    res = pre_flight_checks(symbol)
    logger.info(
        f"[PRE-FLIGHT] {symbol or 'ALL'} ok={res['ok']} "
        f"equity={res['checks'].get('equity')} "
        f"free_margin={res['checks'].get('free_margin')} "
        f"reasons={res['reasons']}"
    )
    return True  # dry-run phase: informational only (P5 se enforce)
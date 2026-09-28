# backend/django/app/risk/circuit_breaker.py — P5 Circuit Breaker (fail-closed, LIVE)
# POLICY nằm ở đây; %/giới hạn đọc DUY NHẤT từ PropFirmRules.yaml. Đọc/ghi
# AccountState uỷ cho utils/db/{get,mutation} — giữ tách Strategy/Risk/Execution.

import logging
from datetime import datetime

from django.db import transaction

from app.utils.constants import rule, TIMEZONE
from app.utils.api.account import get_equity
from app.utils.db.get import get_account_state
from app.utils.db.mutation import update_account_state

logger = logging.getLogger(__name__)


def snapshot(account=None, open_positions=None):
    """P5 — Chụp trạng thái tài khoản, cập nhật AccountState (atomic).

    - daily DD = (starting_equity_day − equity) / starting_equity_day  ≥ 1%  ⇒  trading_day_locked=True
    - total DD = (peak_equity_total − equity) / peak_equity_total     ≥ 3%  ⇒  circuit_breaker_tripped=True

    Toàn bộ read-update-write nằm trong 1 giao dịch; get_account_state() dùng
    select_for_update trên CÙNG 1 dòng AccountState → an toàn giữa 3 Celery worker.
    Trả về dict trạng thái; None nếu equity không đọc được (entry sẽ fail-closed).
    """
    daily_dd_max = float(rule('MAX_DAILY_DRAWDOWN', 0.01))
    total_dd_max = float(rule('MAX_TOTAL_DRAWDOWN', 0.03))

    if account is not None and account.get('equity') is not None:
        equity = float(account['equity'])
    else:
        equity = get_equity()
    if equity is None or equity <= 0:
        logger.warning("[BREAKER] equity unavailable - skip snapshot")
        return None

    today = datetime.now(TIMEZONE).date()

    with transaction.atomic():
        state = get_account_state(lock=True, day=today)

        new_day = (state.day is None) or (state.day != today) or (state.starting_equity_day is None)
        if new_day:
            state.day = today
            fields = {
                'starting_equity_day': equity,
                'daily_pnl': 0.0,
                'trading_day_locked': False,
            }
        else:
            fields = {}

        if state.peak_equity_total is None or equity > state.peak_equity_total:
            fields['peak_equity_total'] = equity

        starting = fields.get('starting_equity_day', state.starting_equity_day)
        peak = fields.get('peak_equity_total', state.peak_equity_total)

        daily_pnl = equity - starting if starting else 0.0
        daily_dd_pct = (starting - equity) / starting if starting else 0.0
        total_dd_pct = (peak - equity) / peak if peak else 0.0

        fields.update({
            'equity_last': equity,
            'daily_pnl': daily_pnl,
            'total_drawdown_pct': total_dd_pct,
        })

        if state.trading_day_locked or daily_dd_pct >= daily_dd_max:
            fields['trading_day_locked'] = True
            if daily_dd_pct >= daily_dd_max and not state.trading_day_locked:
                logger.warning(
                    f"[BREAKER] TRADING DAY LOCKED (trading_day_locked=True) — "
                    f"daily DD {daily_dd_pct:.4%} >= {daily_dd_max:.2%} "
                    f"(equity {equity:g} vs start {starting:g})"
                )

        if state.circuit_breaker_tripped or total_dd_pct >= total_dd_max:
            fields['circuit_breaker_tripped'] = True
            if total_dd_pct >= total_dd_max and not state.circuit_breaker_tripped:
                logger.critical(
                    f"[BREAKER] CIRCUIT BREAKER TRIPPED (circuit_breaker_tripped=True) — "
                    f"total DD {total_dd_pct:.4%} >= {total_dd_max:.2%} "
                    f"(from peak {peak:g})"
                )

        state = update_account_state(state=state, **fields)

        return {
            'day': state.day.isoformat() if state.day else None,
            'starting_equity_day': state.starting_equity_day,
            'peak_equity_total': state.peak_equity_total,
            'equity_last': state.equity_last,
            'daily_pnl': state.daily_pnl,
            'total_drawdown_pct': state.total_drawdown_pct,
            'trading_day_locked': state.trading_day_locked,
            'circuit_breaker_tripped': state.circuit_breaker_tripped,
            'updated_at': state.updated_at,
        }
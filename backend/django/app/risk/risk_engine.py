# backend/django/app/risk/risk_engine.py — P4 position sizing (DRY-RUN)

import logging
import math

from app.utils.api.account import get_equity
from app.utils.api.data import symbol_info
from app.utils.arithmetics import (
    notional_from_risk,
    lots_from_notional,
    lots_with_min_guard,
)
from app.utils.constants import rule

logger = logging.getLogger(__name__)


def _scalar(value, default):
    """Ép giá trị có thể là pandas Series (1 hàng) hoặc None về float mạnh mẽ."""
    if value is None:
        return default
    if hasattr(value, 'iloc'):
        try:
            return float(value.iloc[0])
        except Exception:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def risk_engine(symbol, order_type, price, sl_pct, old_lots=None, dry_run=True):
    """P4 — Dynamic Position Sizer theo % equity. KHONG dat lenh.

    equity -> risk_usd = equity x RISK_PER_TRADE
    notional = risk_usd / |sl_pct|
    lots_new = notional / (contract_size x price)
    lots_new < volume_min  =>  action='SKIP' (khong lam tron len).

    Tra dict quyet dinh; entry.py chi so sanh + log trong DRY-RUN.
    """
    result = {
        'mode': 'DRY-RUN' if dry_run else 'LIVE',
        'symbol': symbol,
        'order_type': order_type,
        'action': 'SKIP',           # fail-closed: mac dinh la khong trade
        'reason': '',
        'equity': None,
        'risk_usd': None,
        'notional': None,
        'lots_new': None,
        'lots_old': old_lots,
        'volume_min': None,
    }

    risk_pct = float(rule('RISK_PER_TRADE', 0.0015))

    equity = get_equity()
    if equity is None or equity <= 0:
        result['reason'] = 'equity unavailable'
        logger.warning(f"[DRY] {symbol}: {result['reason']} - skip sizing")
        return result

    result['equity'] = equity
    risk_usd = equity * risk_pct
    try:
        notional = notional_from_risk(risk_usd, sl_pct)
    except ValueError as e:
        result['reason'] = f'invalid sl_pct: {e}'
        logger.warning(f"[DRY] {symbol}: {result['reason']}")
        return result
    result['risk_usd'] = risk_usd
    result['notional'] = notional

    info = symbol_info(symbol)
    if info is None or info.empty:
        result['reason'] = 'symbol info unavailable'
        logger.warning(f"[DRY] {symbol}: {result['reason']} - skip sizing")
        return result

    contract_size = _scalar(info.get('trade_contract_size'), 100000)
    volume_min = _scalar(info.get('volume_min'), 0.01)
    result['volume_min'] = volume_min

    try:
        lots_new = lots_from_notional(notional, contract_size, float(price))
    except (TypeError, ValueError) as e:
        result['reason'] = f'bad price/contract: {e}'
        logger.warning(f"[DRY] {symbol}: {result['reason']}")
        return result

    # P5 — MT5 tu choi volume khong dung volume_step (retcode 10014): lam tron XUONG
    volume_step = _scalar(info.get('volume_step'), 0.01)
    if volume_step and volume_step > 0:
        lots_new = math.floor(lots_new / volume_step + 1e-9) * volume_step
    result['lots_new'] = lots_new

    lots_final = lots_with_min_guard(lots_new, volume_min)
    if lots_final is None:
        result['reason'] = (f"lots {lots_new:g} < volume_min {volume_min:g} "
                            f"(sub-minimum - khong lam tron len)")
        logger.warning(f"[DRY] {symbol} equity={equity:g} risk_usd={risk_usd:g} "
                       f"lots={lots_new:g} (old={old_lots}) -> SKIP: below volume_min")
        return result

    # --- Nhanh PROCEED (dry-run chi quan sat) ---
    result['action'] = 'PROCEED'
    result['reason'] = 'sizing ok'
    result['restricted_symbol'] = symbol in (rule('RESTRICTED_SYMBOLS', []) or [])

    tag = 'DRY' if dry_run else 'LIVE'
    logger.info(f"[{tag}] {symbol} equity={equity:g} risk_usd={risk_usd:g} "
                f"lots={lots_new:g} (old={old_lots})")
    return result
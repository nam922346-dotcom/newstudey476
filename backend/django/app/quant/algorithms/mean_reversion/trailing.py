# backend/django/app/quant/algorithms/mean_reversion/trailing.py

import traceback
import logging
from dotenv import load_dotenv
from datetime import datetime
from time import perf_counter

import pandas as pd

from app.utils.arithmetics import (
    get_price_at_pnl,
    get_pnl_at_price
)
from app.utils.constants import TIMEZONE
from app.utils.api.positions import get_positions
from app.utils.api.order import modify_sl_tp
from app.utils.api.account import get_equity
from app.nexus.models import PositionSnapshot, TradeClosePricesMutation
from app.utils.db.get import get_trade_with_mutations
from app.quant.algorithms.mean_reversion.config import (
    TRAILING_STOP_STEPS,
    MAX_TRAILING_MUTATIONS_PER_CYCLE,
)

load_dotenv()
logger = logging.getLogger(__name__)

EPSILON = 1e-4  # Define an appropriate epsilon value

# P6 - cache vi the qua cac chu ky: loai bo ve da dong truoc moi modify_sl_tp
# de khong bao gio modify lai ve khong con mo (khong retry trong cung chu ky 15s).
cached_positions = {}


def _drop_closed_positions(current_tickets):
    """Loai bo khoi cache cac ticket khong con la vi the mo hien tai."""
    closed = [t for t in list(cached_positions) if t not in current_tickets]
    for t in closed:
        cached_positions.pop(t, None)
    if closed:
        logger.info(f"[TRAILING] dropped {len(closed)} closed position(s): {closed}")
    return len(closed)


def _risk_unit_for(trade):
    """Don vi R = trade.risk_usd (P5); fallback trade.capital cho lenh cu chua co risk_usd."""
    risk_usd = getattr(trade, 'risk_usd', None)
    if risk_usd and risk_usd > 0:
        return risk_usd
    capital = getattr(trade, 'capital', None)
    if capital and capital > 0:
        return capital
    return None


def _flush_mutations(mutations):
    if not mutations:
        return
    TradeClosePricesMutation.objects.bulk_create(mutations)
    logger.info(f"[TRAILING] mutation batch written: {len(mutations)} rows")
    mutations.clear()


def trailing_stop_algorithm():
    """
    Continuously monitors open trades, detects closed trades, manages trailing stops,
    and sends notifications. Utilizes a cached state to detect changes in open positions
    and interacts with the MT5 API and Django models.

    P6 - trailing theo moc R (multiples of risk_usd), don dieu nghiem ngat,
    khong retry modify trong cung chu ky, ghi mutation theo batch.
    """

    try:
        current_time = datetime.now(TIMEZONE).replace(microsecond=0)
        positions = get_positions()

        # P6 - loai bo ve da dong khoi cache truoc khi xu ly chu ky.
        current_tickets = set(positions['ticket'].values) if not positions.empty else set()
        _drop_closed_positions(current_tickets)

        if positions.empty:
            logger.info('No positions found')
            return

        equity = get_equity()  # fetched once per cycle, shared by all snapshots
        snapshots = []
        mutations = []

        for index, position in positions.iterrows():
            logger.info('Starting position timer')
            position_start_time = perf_counter()  # Start timing for the position

            # Check if the position ticket exists in trades dict
            trade_with_mutations = get_trade_with_mutations(position.ticket)

            if trade_with_mutations is None:
                error_msg = f"No trade found with ticket {position.ticket}"
                logger.error(error_msg)
                continue

            trade = trade_with_mutations.get("trade")
            trade_mutations = trade_with_mutations.get("mutations", [])

            # --- P2 telemetry: one PositionSnapshot per open position per cycle ---
            snapshots.append(PositionSnapshot(
                trade=trade,
                ts=current_time,
                price_current=float(position.price_current) if pd.notna(position.price_current) else None,
                profit_floating=float(position.profit) if pd.notna(position.profit) else None,
                # MT5 position.profit is the floating PnL; commission is booked on the
                # closing deal only, so profit_excl_comm equals profit_floating while
                # the position is open. Refinement in a later phase.
                profit_excl_comm=float(position.profit) if pd.notna(position.profit) else None,
                equity=equity,
                sl_current=float(position.sl) if pd.notna(position.sl) and position.sl else None,
                tp_current=float(position.tp) if pd.notna(position.tp) and position.tp else None,
            ))

            # P6 - anchor R: risk_usd (P5) neu co, fallback capital.
            risk_unit = _risk_unit_for(trade)
            if risk_unit is None:
                logger.warning(f"No risk unit for trade ticket {position.ticket}: "
                               f"risk_usd={getattr(trade, 'risk_usd', None)} capital={trade.capital}")
                continue

            current_sl_pnl, _ = get_pnl_at_price(
                position.sl, position.price_open, trade.position_size_usd, trade.leverage,
                trade.type, trade.order_commission
            )

            # P6 - duyet NGUOC: bac trigger cao nhat dat duoc se thang va khoa.
            for trailing_step in reversed(TRAILING_STOP_STEPS):
                trigger_risk_multiple = float(trailing_step['trigger_risk_multiple'])
                new_sl_risk_multiple = float(trailing_step['new_sl_risk_multiple'])

                # P6 - trigger_pnl / new_sl_pnl = R x multiple (khong con capital).
                trigger_pnl = risk_unit * trigger_risk_multiple
                new_sl_pnl = risk_unit * new_sl_risk_multiple

                new_sl_price, new_sl_price_excl = get_price_at_pnl(
                    desired_pnl=new_sl_pnl,
                    entry_price=position.price_open,
                    commission=trade.order_commission,
                    order_size_usd=trade.position_size_usd,
                    leverage=trade.leverage,
                    type=trade.type
                )

                nothing_is_none = (
                    pd.notna(position.profit) and pd.notna(position.sl)
                    and new_sl_price is not None
                )

                # Profit floating dat moc trigger cua bac nay.
                if nothing_is_none and position.profit >= trigger_pnl:
                    # P6 - bao ve don dieu NGHIEM NGAT: chi nhan new_sl TOT HON
                    # (BUY new_sl > sl + eps / SELL new_sl < sl - eps); khong day SL lui.
                    if (trade.type == 'BUY' and new_sl_price > position.sl + EPSILON) or \
                       (trade.type == 'SELL' and new_sl_price < position.sl - EPSILON):
                        sl_info = {
                            'event': 'trailing_stop_triggered',
                            'risk_unit': f"${risk_unit:.5f}",
                            'trigger_risk_multiple': f"{trigger_risk_multiple:.2f}R",
                            'new_sl_risk_multiple': f"{new_sl_risk_multiple:.2f}R",
                            'trigger_pnl': f"${trigger_pnl:.5f}",
                            'new_sl_pnl': f"${new_sl_pnl:.5f}",
                            'position_data': {
                                'symbol': position.symbol,
                                'trade_open_date': position.time.isoformat(),
                                'type': trade.type,
                                'entry_price': f"${position.price_open:.5f}",
                                'current_price': f"${position.price_current:.5f}",
                            },
                            'current_pnl': {
                                'current_pnl': f"${position.profit:.5f}",
                            },
                            'old_sl': {
                                'old_sl': f"${position.sl:.5f}",
                                'pnl_at_old_sl': f"${current_sl_pnl:.5f}",
                            },
                            'new_sl': {
                                'new_sl': f"${new_sl_price:.5f}",
                                'pnl_at_new_sl': f"${new_sl_pnl:.5f}",
                                'new_sl_excluding_commission': f"${new_sl_price_excl:.5f}",
                            }
                        }

                        # P6 - chac chan ve van mo ngay truoc modify (neu da dong
                        # giua chu ky thi bo qua, vong sau xu ly).
                        if int(position.ticket) not in current_tickets:
                            logger.info({'message': 'position no longer open, skip modify',
                                         'ticket': int(position.ticket)})
                            break

                        # Modify the Stop Loss and Take Profit
                        modify_request = modify_sl_tp(position, new_sl_price)
                        if modify_request is not None:
                            logger.info({'message': 'successfully modified sl from mt5 api',
                                         'modify_request': modify_request, 'sl_info': sl_info})

                            # P6 - mutation insert theo BATCH (<= N dong / chu ky).
                            mutations.append(TradeClosePricesMutation(
                                trade=trade,
                                mutation_time=current_time,
                                mutation_price=position.price_current,
                                new_sl_price=new_sl_price,
                                pnl_at_new_sl_price=new_sl_pnl,
                            ))
                            if len(mutations) >= MAX_TRAILING_MUTATIONS_PER_CYCLE:
                                _flush_mutations(mutations)
                        else:
                            # P6 - KHONG retry chop nhoang trong cung chu ky:
                            # de vong sau (15s) xu ly lai khi tinh trang on dinh.
                            logger.info({'message': 'failed to modify sl from mt5 api (defer to next cycle)',
                                         'sl_info': sl_info})

                        break  # Da xu ly bac trigger cao nhat dat duoc

                    # else: new_sl chua TOT HON sl hien tai -> fall-through moc thap hon
                # else: profit chua dat trigger bac nay -> thu bac thap hon

            # End timing for the position
            position_end_time = perf_counter()
            position_duration = position_end_time - position_start_time
            logger.info(f"Processed position {position.ticket} in {position_duration:.4f} seconds.")

        # P2 telemetry + P6 mutations: ghi mot lan cuoi chu ky.
        _flush_mutations(mutations)
        if snapshots:
            PositionSnapshot.objects.bulk_create(snapshots, batch_size=100)
            logger.info(f"Recorded {len(snapshots)} position snapshots @ {current_time.isoformat()}")

        # P6 - dong bo cache voi danh sach vi the dang mo (chuan bi chu ky sau).
        cached_positions.clear()
        for _, position in positions.iterrows():
            cached_positions[int(position.ticket)] = position

    except Exception as e:
        error_msg = f"Exception in trailing_stop_algorithm: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
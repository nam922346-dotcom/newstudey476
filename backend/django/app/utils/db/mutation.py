import traceback
import logging
import pandas as pd

from django.db import transaction

from app.utils.api.data import symbol_info
from app.nexus.models import Trade, TradeClosePricesMutation
from app.utils.db.get import get_account_state

logger = logging.getLogger(__name__)

def mutate_trade(position, current_time, new_sl_price_including_commission, pnl_at_new_sl_including_commission):
    try:        
        with transaction.atomic():
            trade = Trade.objects.get(transaction_broker_id=position.ticket)
            TradeClosePricesMutation.objects.create(
                trade=trade,
                mutation_time=current_time,
                mutation_price=position.price_current,
                new_sl_price=new_sl_price_including_commission,
                pnl_at_new_sl_price=pnl_at_new_sl_including_commission
            )
            logger.info(f"Created TradeClosePricesMutation for Trade ID {trade.id}")
            
    except Trade.DoesNotExist:
        error_msg = f"No Trade found with transaction_broker_id {position.ticket}"
        logger.error(error_msg)

    except Exception as e:
        error_msg = f"Error creating TradeClosePricesMutation: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)


def update_account_state(day=None, state=None, **fields):
    """Ghi loạt field lên AccountState hiện tại trong 1 lần save.

    - `state` truyền vào = instance đã lock bằng select_for_update (caller
      circuit_breaker gọi trong transaction.atomic()) → ghi chính instance đó,
      không truy vấn thêm.
    - `state=None` → tự get KHÔNG lock (chỉ cho thao tác ops không cạnh tranh);
      trả None nếu chưa có dòng.
    """
    if state is None:
        state = get_account_state(lock=False, day=day)
        if state is None:
            return None
    for key, value in fields.items():
        if hasattr(state, key):
            setattr(state, key, value)
    state.save()
    return state

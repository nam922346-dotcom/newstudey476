import traceback
import logging
from typing import Optional, Dict, Any

from django.db import IntegrityError

from app.nexus.models import Trade, TradeClosePricesMutation, AccountState

logger = logging.getLogger(__name__)

def get_trade_with_mutations(ticket: int) -> Optional[Dict[str, Any]]:
    try:
        trade = Trade.objects.filter(transaction_broker_id=ticket).first()
        if not trade:
            logger.error(f"No trade found with ticket {ticket}")
            return None

        mutations = TradeClosePricesMutation.objects.filter(trade=trade)
        # Convert queryset to list if you need to serialize it
        mutations_list = list(mutations.values())
        
        return {
            "trade": trade,
            "mutations": mutations_list
        }
    except Exception as e:
        error_msg = f"Error fetching trade with mutations: {e}\n{traceback.format_exc()}"
        logger.error(error_msg)
        return None


def get_account_state(lock=False, day=None):
    """Trả AccountState hiện tại (singleton 1 dòng cho tài khoản).

    - lock=True  → select_for_update; PHẢI gọi trong transaction.atomic()
      (dùng cho nơi ghi — chống race giữa mấy Celery worker). Tạo dòng nếu
      chưa có (bắt IntegrityError nếu worker khác tạo trước).
    - lock=False → read-only, không tạo dòng, trả None nếu chưa có.
    """
    from datetime import datetime
    from app.utils.constants import TIMEZONE

    if day is None:
        day = datetime.now(TIMEZONE).date()

    qs = AccountState.objects.all()
    if lock:
        qs = qs.select_for_update()
    state = qs.first()
    if state is None:
        if not lock:
            return None
        try:
            state = AccountState.objects.create(day=day)
        except IntegrityError:
            state = AccountState.objects.get(day=day)
    return state
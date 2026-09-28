# backend/django/app/quant/management/commands/risk_status.py
# Lệnh dev: docker compose exec django python manage.py risk_status

from django.core.management.base import BaseCommand

from app.utils.constants import rule
from app.utils.db.get import get_account_state


class Command(BaseCommand):
    help = 'In trạng thái AccountState (risk engine / circuit breaker) một cách đọc được.'

    def handle(self, *args, **options):
        state = get_account_state(lock=False)

        self.stdout.write("===== ACCOUNT STATE (Risk / Circuit Breaker) =====")
        if state is None:
            self.stdout.write(self.style.WARNING(
                "Chưa có AccountState — chưa có lần snapshot() nào (market mở mới có)."
            ))
            return

        dd_txt = f"{state.total_drawdown_pct:.4%}" if state.total_drawdown_pct is not None else "None"
        self.stdout.write(f"day                     : {state.day}")
        self.stdout.write(f"starting_equity_day     : {state.starting_equity_day}")
        self.stdout.write(f"peak_equity_total       : {state.peak_equity_total}")
        self.stdout.write(f"equity_last             : {state.equity_last}")
        self.stdout.write(f"daily_pnl               : {state.daily_pnl}")
        self.stdout.write(f"total_drawdown_pct      : {dd_txt}")
        self.stdout.write(f"trading_day_locked      : {state.trading_day_locked}")
        self.stdout.write(f"circuit_breaker_tripped : {state.circuit_breaker_tripped}")
        self.stdout.write(f"updated_at              : {state.updated_at}")

        self.stdout.write("")
        self.stdout.write(f"threshold daily (MAX_DAILY_DRAWDOWN) : {float(rule('MAX_DAILY_DRAWDOWN', 0.01)):.2%}")
        self.stdout.write(f"threshold total (MAX_TOTAL_DRAWDOWN) : {float(rule('MAX_TOTAL_DRAWDOWN', 0.03)):.2%}")
        self.stdout.write(f"risk/trade    (RISK_PER_TRADE)      : {float(rule('RISK_PER_TRADE', 0.0015)):.4%}")

        if state.circuit_breaker_tripped:
            self.stdout.write(self.style.ERROR("CIRCUIT BREAKER: TRIPPED — chặn mọi entry"))
        elif state.trading_day_locked:
            self.stdout.write(self.style.WARNING("TRADING DAY: LOCKED — chặn entry hôm nay"))
        else:
            self.stdout.write(self.style.SUCCESS("CỬA MỞ — entry được phép (nếu pre-flight OK)"))
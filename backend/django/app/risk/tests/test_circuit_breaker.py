# backend/django/app/risk/tests/test_circuit_breaker.py
# P8 — unit tests cho circuit_breaker.snapshot(): seed ngày, peak, daily 1% lock,
# total 3% trip, sticky, reset ngày mới. Không dùng DB (fake get/update AccountState).
import datetime as _dt

import pytest


def _apply_fields(state, fields):
    for k, v in fields.items():
        if hasattr(state, k):
            setattr(state, k, v)
    return state


class FakeAccountState:
    """Bản fake của instance AccountState (model nằm trong app.nexus.models)."""

    def __init__(self, **kwargs):
        self.day = None
        self.starting_equity_day = None
        self.peak_equity_total = None
        self.equity_last = None
        self.daily_pnl = 0.0
        self.total_drawdown_pct = 0.0
        self.trading_day_locked = False
        self.circuit_breaker_tripped = False
        self.updated_at = _dt.datetime(2026, 9, 29, 8, 0)
        for k, v in kwargs.items():
            setattr(self, k, v)


class FixedClock:
    NOW = _dt.datetime(2026, 9, 29, 12, 0, tzinfo=_dt.timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.NOW

    @classmethod
    def set(cls, dt):
        cls.NOW = dt


@pytest.fixture
def cb_mod(loader, defaults):
    mod = loader('circuit_breaker_ut', 'circuit_breaker.py')
    mod.rule = lambda key, default=None: defaults.get(key, default)
    mod.get_equity = lambda: None
    mod.get_account_state = lambda lock=False, day=None: FakeAccountState()
    mod.update_account_state = lambda state=None, day=None, **fields: _apply_fields(state, fields)
    mod.datetime = FixedClock
    return mod


def _hook(cb_mod, monkeypatch, state):
    monkeypatch.setattr(cb_mod, 'get_account_state', lambda lock=False, day=None: state)
    monkeypatch.setattr(cb_mod, 'update_account_state',
                        lambda state=None, day=None, **fields: _apply_fields(state, fields))


def test_equity_unavailable_returns_none(cb_mod, monkeypatch):
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: None)
    assert cb_mod.snapshot() is None
    # Khi equity None/<=0 -> snapshot trả None -> entry fail-closed


def test_first_snapshot_of_day_seeds(cb_mod, monkeypatch):
    st = FakeAccountState()
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 100000.0)
    res = cb_mod.snapshot()
    assert res is not None
    assert res['day'] == '2026-09-29'
    assert res['starting_equity_day'] == pytest.approx(100000.0)
    assert res['peak_equity_total'] == pytest.approx(100000.0)
    assert res['equity_last'] == pytest.approx(100000.0)
    assert res['daily_pnl'] == pytest.approx(0.0)
    assert res['total_drawdown_pct'] == pytest.approx(0.0)
    assert res['trading_day_locked'] is False
    assert res['circuit_breaker_tripped'] is False
    assert set(res.keys()) == {
        'day', 'starting_equity_day', 'peak_equity_total', 'equity_last', 'daily_pnl',
        'total_drawdown_pct', 'trading_day_locked', 'circuit_breaker_tripped', 'updated_at',
    }
    assert res['updated_at'] == st.updated_at


def test_pass_equity_dict_overrides_network(cb_mod, monkeypatch):
    st = FakeAccountState()
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 123.0)  # KHÔNG được dùng
    res = cb_mod.snapshot(account={'equity': 100000.0})
    assert res['equity_last'] == pytest.approx(100000.0)


def test_daily_dd_locks_day(cb_mod, monkeypatch):
    st = FakeAccountState(day=_dt.date(2026, 9, 29),
                          starting_equity_day=100000.0, peak_equity_total=100000.0)
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 98900.0)  # DD 1.1% >= 1%
    res = cb_mod.snapshot()
    assert res['trading_day_locked'] is True
    assert res['daily_pnl'] == pytest.approx(-1100.0)
    assert res['total_drawdown_pct'] == pytest.approx(0.011)
    assert st.trading_day_locked is True
    assert res['circuit_breaker_tripped'] is False


def test_total_dd_trips_breaker(cb_mod, monkeypatch):
    st = FakeAccountState(day=_dt.date(2026, 9, 29),
                          starting_equity_day=100000.0, peak_equity_total=100000.0)
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 96800.0)  # DD 3.2% >= 3%
    res = cb_mod.snapshot()
    assert res['circuit_breaker_tripped'] is True
    assert res['total_drawdown_pct'] == pytest.approx(0.032)


def test_locks_are_sticky(cb_mod, monkeypatch):
    st = FakeAccountState(day=_dt.date(2026, 9, 29),
                          starting_equity_day=100000.0, peak_equity_total=100000.0,
                          trading_day_locked=True)
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 101000.0)  # hồi phục trên đỉnh
    res = cb_mod.snapshot()
    assert res['trading_day_locked'] is True      # khóa một ngày là khóa luôn
    assert res['peak_equity_total'] == pytest.approx(101000.0)
    assert res['total_drawdown_pct'] == pytest.approx(0.0)


def test_peak_updated_when_equity_higher(cb_mod, monkeypatch):
    st = FakeAccountState(day=_dt.date(2026, 9, 29),
                          starting_equity_day=100000.0, peak_equity_total=100000.0)
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 102000.0)
    res = cb_mod.snapshot()
    assert res['peak_equity_total'] == pytest.approx(102000.0)
    assert res['total_drawdown_pct'] == pytest.approx(0.0)
    assert res['daily_pnl'] == pytest.approx(2000.0)


def test_reset_on_new_day(cb_mod, monkeypatch):
    st = FakeAccountState(day=_dt.date(2026, 9, 28),
                          starting_equity_day=90000.0, peak_equity_total=100000.0,
                          trading_day_locked=True)
    _hook(cb_mod, monkeypatch, st)
    monkeypatch.setattr(cb_mod, 'get_equity', lambda: 91000.0)
    FixedClock.set(_dt.datetime(2026, 9, 29, 0, 5, tzinfo=_dt.timezone.utc))
    try:
        res = cb_mod.snapshot()
    finally:
        FixedClock.set(_dt.datetime(2026, 9, 29, 12, 0, tzinfo=_dt.timezone.utc))
    assert res['day'] == '2026-09-29'
    assert res['starting_equity_day'] == pytest.approx(91000.0)   # seed ngày mới
    assert res['trading_day_locked'] is False                      # reset khóa ngày
    assert res['peak_equity_total'] == pytest.approx(100000.0)     # đỉnh giữ qua ngày
    # total DD từ đỉnh = (100000-91000)/100000 = 9% >= 3% -> breaker TRIPPED (đúng thiết kế)
    assert res['circuit_breaker_tripped'] is True
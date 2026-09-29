# backend/django/app/risk/tests/test_pre_flight.py
# P8 — unit tests cho pre_flight.py (4 nhóm check + cooldown + blackout + gate informational).
import time
import datetime as _dt

import pytest

FIXED_NOW = _dt.datetime(2026, 9, 28, 10, 0, tzinfo=_dt.timezone.utc)
BLACKOUT_MON = [{'weekday': FIXED_NOW.weekday(), 'start': '00:00', 'end': '24:00'}]


def _money_account(equity=100000.0, margin_free=90000.0):
    return {'equity': equity, 'margin_free': margin_free, 'balance': equity}


@pytest.fixture
def pf_mod(loader, defaults):
    mod = loader('pre_flight_ut', 'pre_flight.py')
    mod.rule = lambda key, default=None: defaults.get(key, default)
    mod._last_entry_at = 0.0
    return mod


def test_all_checks_pass(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is True
    assert res['reasons'] == []
    assert res['checks']['cooldown_remaining'] == 0.0


def test_equity_unavailable(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: None)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is False
    assert any('equity' in r for r in res['reasons'])


def test_free_margin_below_threshold(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account(margin_free=10000.0))
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is False
    assert any('free_margin' in r for r in res['reasons'])
    assert res['checks']['free_margin_ok'] is False


def test_cooldown_active(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())
    pf_mod._last_entry_at = time.time()
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is False
    assert any('cooldown' in r for r in res['reasons'])
    assert res['checks']['cooldown_remaining'] > 0


def test_cooldown_elapsed_after_60s(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())
    pf_mod._last_entry_at = time.time() - 61
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is True


def test_blackout_window_blocks(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())

    class FakeNow:
        @classmethod
        def now(cls, tz=None):
            return FIXED_NOW

    monkeypatch.setattr(pf_mod, 'datetime', FakeNow)
    monkeypatch.setattr(
        pf_mod, 'rule',
        lambda k, d=None: BLACKOUT_MON if k == 'BLACKOUT_WINDOWS' else 0.20 if k == 'MIN_FREE_MARGIN_PCT' else d,
    )
    res = pf_mod.pre_flight_checks('EURUSDm')
    assert res['ok'] is False
    assert res['checks']['blackout_ok'] is False
    assert any('blackout' in r for r in res['reasons'])


def test_enter_pre_flight_gate_is_informational(pf_mod, monkeypatch):
    monkeypatch.setattr(pf_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(pf_mod, 'get_account', lambda: _money_account())
    assert pf_mod.enter_pre_flight_gate('EURUSDm') is True
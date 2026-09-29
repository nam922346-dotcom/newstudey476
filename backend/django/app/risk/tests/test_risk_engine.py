# backend/django/app/risk/tests/test_risk_engine.py
# P8 — unit tests cho risk_engine.py (sizing % equity, fail-closed, volume_step).
import math

import pytest


class FakeSymbolInfo:
    """Stand-in cho 1-hàng pandas DataFrame mà symbol_info() thật trả về."""

    def __init__(self, trade_contract_size=100000, volume_min=0.01, volume_step=0.01):
        self._data = {
            'trade_contract_size': trade_contract_size,
            'volume_min': volume_min,
            'volume_step': volume_step,
        }
        self.empty = False

    def get(self, key, default=None):
        return self._data.get(key, default)


@pytest.fixture
def re_mod(loader, defaults):
    mod = loader('risk_engine_ut', 'risk_engine.py')
    mod.rule = lambda key, default=None: defaults.get(key, default)
    return mod


def test_equity_unavailable_fail_closed(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: None)
    res = re_mod.risk_engine('EURUSDm', 'BUY', 1.10, 0.0025)
    assert res['action'] == 'SKIP'
    assert 'equity' in res['reason']
    assert res['mode'] == 'DRY-RUN'


def test_sizing_from_equity_risk_pct(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: FakeSymbolInfo())
    res = re_mod.risk_engine('EURUSDm', 'BUY', 1.10, 0.0025, dry_run=False)
    assert res['action'] == 'PROCEED'
    assert res['mode'] == 'LIVE'
    assert res['equity'] == pytest.approx(100000.0)
    assert res['risk_usd'] == pytest.approx(150.0)       # 100000 * 0.0015
    assert res['notional'] == pytest.approx(60000.0)     # 150 / 0.0025
    # lots = 60000 / (100000 * 1.10) = 0.54545... floor(0.01) -> 0.54
    assert res['lots_new'] == pytest.approx(0.54)
    assert res['volume_min'] == 0.01


def test_capital_per_trade_does_not_influence_sizing(re_mod, monkeypatch):
    # Bằng chứng P8: sizing phụ thuộc DUY NHẤT equity x RISK_PER_TRADE / |sl_pct|,
    # không có hằng số capital nào tham gia (CAPITAL_PER_TRADE chỉ còn legacy).
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: FakeSymbolInfo())
    res = re_mod.risk_engine('USDJPYm', 'SELL', 150.0, 0.0025)
    risk_pct = 0.0015
    assert res['risk_usd'] == pytest.approx(100000.0 * risk_pct)
    assert res['notional'] == pytest.approx(res['risk_usd'] / 0.0025)
    assert res['lots_new'] is not None
    assert 'capital' not in res


def test_floor_to_volume_step(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: FakeSymbolInfo(volume_step=0.01))
    res = re_mod.risk_engine('EURUSDm', 'BUY', 1.10, 0.0025)
    raw = 60000.0 / (100000 * 1.10)
    expect = math.floor(raw / 0.01 + 1e-9) * 0.01
    assert res['lots_new'] == pytest.approx(expect)
    assert res['lots_new'] <= raw + 1e-9  # không bao giờ làm tròn LÊN (chống retcode 10014)


def test_below_volume_min_skip(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 1000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: FakeSymbolInfo(volume_min=0.01))
    res = re_mod.risk_engine('XAUUSDm', 'BUY', 2500.0, 0.0025)
    assert res['action'] == 'SKIP'
    assert 'volume_min' in res['reason']


def test_invalid_sl_pct(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    res = re_mod.risk_engine('EURUSDm', 'BUY', 1.10, 0.0)
    assert res['action'] == 'SKIP'
    assert 'sl_pct' in res['reason']


def test_symbol_info_unavailable(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: None)
    res = re_mod.risk_engine('EURUSDm', 'BUY', 1.10, 0.0025)
    assert res['action'] == 'SKIP'
    assert 'symbol info' in res['reason']


def test_restricted_symbol_flag(re_mod, monkeypatch):
    monkeypatch.setattr(re_mod, 'get_equity', lambda: 100000.0)
    monkeypatch.setattr(re_mod, 'symbol_info', lambda s: FakeSymbolInfo())
    monkeypatch.setattr(
        re_mod, 'rule',
        lambda k, d=None: ['USOILm'] if k == 'RESTRICTED_SYMBOLS' else 0.0015 if k == 'RISK_PER_TRADE' else d,
    )
    res = re_mod.risk_engine('USOILm', 'BUY', 60.0, 0.0025)
    assert res['action'] == 'PROCEED'
    assert res['restricted_symbol'] is True
# backend/django/app/risk/tests/conftest.py
# P8 — pytest hermetic cho risk layer. Seed fake modules vào sys.modules TRƯỚC khi nạp
# module-under-test bằng importlib, nên KHÔNG cần Django / MT5 / Postgres (chạy trên PC dev).
import sys
import types
import datetime as _dt
import importlib.util
from pathlib import Path

import pytest


_DEFAULT_RULES = {
    'RISK_PER_TRADE': 0.0015,          # PropFirmRules.yaml (single source, P4)
    'MAX_DAILY_DRAWDOWN': 0.01,
    'MAX_TOTAL_DRAWDOWN': 0.03,
    'MIN_FREE_MARGIN_PCT': 0.20,
    'COOLDOWN_SECONDS': 60,
    'BLACKOUT_WINDOWS': [],
    'RESTRICTED_SYMBOLS': [],
}


def _mod(name, **attrs):
    m = types.ModuleType(f'<fake {name}>')
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def _notional_from_risk(risk_usd, sl_pct):
    if sl_pct is None or sl_pct == 0:
        raise ValueError('sl_pct must be a non-zero fractional stop distance')
    return risk_usd / abs(sl_pct)


def _lots_from_notional(notional_usd, contract_size, price):
    if not contract_size or contract_size <= 0 or not price or price <= 0:
        raise ValueError('contract_size and price must be positive')
    return notional_usd / (contract_size * price)


def _lots_with_min_guard(lots, volume_min):
    if volume_min is None or volume_min <= 0:
        volume_min = 0.01
    if lots is None or lots < volume_min:
        return None
    return lots


class _FakeAtomic:
    """No-op context manager thay django.db.transaction.atomic()."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _install_fakes():
    # LUÔN ghi đè (idempotent) — không early-return: nếu pytest/native đã import package `app`
    # thật vào sys.modules trước conftest (khi pytest.ini đổi rootdir), ta vẫn phải thay bằng fake.
    utc = _dt.timezone.utc
    sys.modules['django'] = _mod('django')
    sys.modules['django.db'] = _mod('django.db')
    sys.modules['django.db'].transaction = types.SimpleNamespace(atomic=_FakeAtomic)
    sys.modules['app'] = _mod('app', __path__=[])
    sys.modules['app.risk'] = _mod('app.risk', __path__=[])
    sys.modules['app.utils'] = _mod('app.utils', __path__=[])
    sys.modules['app.utils.constants'] = _mod(
        'app.utils.constants',
        rule=lambda key, default=None: _DEFAULT_RULES.get(key, default),
        TIMEZONE=utc,
    )
    sys.modules['app.utils.api'] = _mod('app.utils.api', __path__=[])
    sys.modules['app.utils.api.account'] = _mod(
        'app.utils.api.account',
        get_account=lambda: None,
        get_equity=lambda: None,
    )
    sys.modules['app.utils.api.data'] = _mod(
        'app.utils.api.data',
        symbol_info=lambda symbol: None,
    )
    sys.modules['app.utils.arithmetics'] = _mod(
        'app.utils.arithmetics',
        notional_from_risk=_notional_from_risk,
        lots_from_notional=_lots_from_notional,
        lots_with_min_guard=_lots_with_min_guard,
    )
    sys.modules['app.utils.db'] = _mod('app.utils.db', __path__=[])
    sys.modules['app.utils.db.get'] = _mod(
        'app.utils.db.get',
        get_account_state=lambda lock=False, day=None: None,
    )
    sys.modules['app.utils.db.mutation'] = _mod(
        'app.utils.db.mutation',
        update_account_state=lambda state=None, day=None, **fields: state,
    )


_install_fakes()


def load_module(name, rel_path):
    """Nạp module-under-test theo đường dẫn (rel tới app/risk/) mà KHÔNG import package `app`."""
    path = Path(__file__).resolve().parent.parent / rel_path
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def loader():
    return load_module


@pytest.fixture
def defaults():
    return dict(_DEFAULT_RULES)
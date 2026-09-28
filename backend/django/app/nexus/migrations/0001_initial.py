# backend/django/app/nexus/migrations/0001_initial.py
# P5 — Baseline = DB thực tế đang chạy (P2 đã tạo bảng bằng SQL; file migration
# nexus không có trong repo). Dùng cho: fresh-deploy (migrate thường) hoặc
# live (migrate nexus --fake-initial — bảng đã tồn tại).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Trade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transaction_broker_id', models.CharField(max_length=100)),
                ('symbol', models.CharField(max_length=10)),
                ('entry_time', models.DateTimeField()),
                ('entry_price', models.FloatField()),
                ('type', models.CharField(choices=[('BUY', 'Buy'), ('SELL', 'Sell')], max_length=4)),
                ('position_size_usd', models.FloatField()),
                ('capital', models.FloatField()),
                ('leverage', models.FloatField(default=500)),
                ('order_volume', models.FloatField(blank=True, null=True)),
                ('liquidity_price', models.FloatField()),
                ('break_even_price', models.FloatField()),
                ('order_commission', models.FloatField()),
                ('close_time', models.DateTimeField(blank=True, null=True)),
                ('close_price', models.FloatField(blank=True, null=True)),
                ('pnl', models.FloatField(blank=True, null=True)),
                ('pnl_excluding_commission', models.FloatField(blank=True, null=True)),
                ('max_drawdown', models.FloatField(blank=True, null=True)),
                ('max_profit', models.FloatField(blank=True, null=True)),
                ('closing_reason', models.CharField(blank=True, choices=[('TP', 'Take Profit'), ('SL', 'Stop Loss'), ('MANUAL', 'Manual'), ('LIQUIDATION', 'Liquidation'), ('OTHER', 'Other')], max_length=50, null=True)),
                ('strategy', models.CharField(max_length=50)),
                ('broker', models.CharField(max_length=50)),
                ('market_type', models.CharField(choices=[('FOREX', 'Forex'), ('CRYPTO', 'Crypto'), ('OTHER', 'Other')], max_length=50)),
                ('timeframe', models.CharField(choices=[('1M', '1 Minute'), ('5M', '5 Minutes'), ('15M', '15 Minutes'), ('1H', '1 Hour'), ('4H', '4 Hours'), ('1D', '1 Day')], max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name='TradeClosePricesMutation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mutation_time', models.DateTimeField(auto_now_add=True)),
                ('mutation_price', models.FloatField(blank=True, null=True)),
                ('new_tp_price', models.FloatField(blank=True, null=True)),
                ('new_sl_price', models.FloatField(blank=True, null=True)),
                ('pnl_at_new_tp_price', models.FloatField(blank=True, null=True)),
                ('pnl_at_new_sl_price', models.FloatField(blank=True, null=True)),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='close_prices_mutations', to='nexus.trade')),
            ],
            options={
                'verbose_name': 'Trade Close Prices Mutation',
                'verbose_name_plural': 'Trade Close Prices Mutations',
                'ordering': ['mutation_time'],
            },
        ),
        migrations.CreateModel(
            name='PositionSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ts', models.DateTimeField(db_index=True)),
                ('price_current', models.FloatField(blank=True, null=True)),
                ('profit_floating', models.FloatField(blank=True, null=True)),
                ('profit_excl_comm', models.FloatField(blank=True, null=True)),
                ('equity', models.FloatField(blank=True, null=True)),
                ('sl_current', models.FloatField(blank=True, null=True)),
                ('tp_current', models.FloatField(blank=True, null=True)),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='position_snapshots', to='nexus.trade')),
            ],
            options={
                'verbose_name': 'Position Snapshot',
                'verbose_name_plural': 'Position Snapshots',
                'ordering': ['ts'],
                'indexes': [models.Index(fields=['trade', 'ts'], name='snapshot_trade_ts_idx')],
            },
        ),
    ]
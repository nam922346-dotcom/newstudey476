# backend/django/app/nexus/migrations/0002_risk_gate.py
# P5 — Risk Engine + Circuit Breaker: cột rủi ro trên Trade + bảng AccountState.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nexus', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='trade',
            name='equity_at_entry',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='risk_usd',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='trade',
            name='risk_percent',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='AccountState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(unique=True)),
                ('starting_equity_day', models.FloatField(blank=True, null=True)),
                ('peak_equity_total', models.FloatField(blank=True, null=True)),
                ('equity_last', models.FloatField(blank=True, null=True)),
                ('daily_pnl', models.FloatField(default=0.0)),
                ('total_drawdown_pct', models.FloatField(default=0.0)),
                ('trading_day_locked', models.BooleanField(default=False)),
                ('circuit_breaker_tripped', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Account State',
                'verbose_name_plural': 'Account States',
            },
        ),
    ]
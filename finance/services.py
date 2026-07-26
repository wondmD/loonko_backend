"""Finance integration: milk income, health/feed auto expenses (per farm)."""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import F, Sum
from django.utils import timezone


@db_transaction.atomic
def sync_daily_milk_income(farm, day=None, *, force=False):
    """
    Create/update/delete the auto milk-income transaction for a farm+day.
    Amount = sum(morning+evening liters that day) × farm.milk_price_per_liter.
    """
    from finance.models import Transaction
    from milk.models import MilkRecord

    day = day or timezone.localdate()
    source_key = f'milk-income-{day.isoformat()}'

    if not farm or not farm.books_production_income:
        Transaction.objects.filter(
            farm=farm, source_key=source_key, is_auto=True
        ).delete()
        return None

    price = farm.milk_price_per_liter or Decimal('0')
    if price <= 0 and not force:
        Transaction.objects.filter(
            farm=farm, source_key=source_key, is_auto=True
        ).delete()
        return None

    liters = (
        MilkRecord.objects.filter(farm=farm, date=day)
        .annotate(total=F('morning_liters') + F('evening_liters'))
        .aggregate(s=Sum('total'))['s']
        or Decimal('0')
    )
    liters = Decimal(liters)

    if liters <= 0:
        Transaction.objects.filter(
            farm=farm, source_key=source_key, is_auto=True
        ).delete()
        return None

    amount = (liters * price).quantize(Decimal('0.01'))
    currency = farm.currency or 'ETB'
    description = (
        f'Auto milk income: {liters} L × {price} {currency}/L '
        f'(daily production valuation)'
    )

    txn, _ = Transaction.objects.update_or_create(
        farm=farm,
        source_key=source_key,
        defaults={
            'type': Transaction.Type.INCOME,
            'category': Transaction.Category.MILK_PRODUCTION,
            'amount': amount,
            'currency': currency,
            'date': day,
            'description': description,
            'is_auto': True,
            'related_milk_record': None,
        },
    )
    return txn


def sync_milk_income_for_record(milk_record):
    farm = milk_record.farm or getattr(milk_record.cattle, 'farm', None)
    return sync_daily_milk_income(farm, milk_record.date)


def backfill_milk_income(farm=None, days=90):
    from farm.models import Farm

    today = timezone.localdate()
    farms = [farm] if farm is not None else list(Farm.objects.all())
    created = 0
    for f in farms:
        for offset in range(days + 1):
            day = today - timedelta(days=offset)
            txn = sync_daily_milk_income(f, day, force=True)
            if txn:
                created += 1
    return created


def _upsert_linked_expense(*, farm, source_key, category, amount, currency, date, description):
    from finance.models import Transaction

    amount = Decimal(amount or 0)
    if amount <= 0:
        Transaction.objects.filter(farm=farm, source_key=source_key, is_auto=True).delete()
        return None

    txn, _ = Transaction.objects.update_or_create(
        farm=farm,
        source_key=source_key,
        defaults={
            'type': Transaction.Type.EXPENSE,
            'category': category,
            'amount': amount.quantize(Decimal('0.01')),
            'currency': currency,
            'date': date,
            'description': description,
            'is_auto': True,
            'related_milk_record': None,
        },
    )
    return txn


def sync_vaccination_expense(vaccination):
    from finance.models import Transaction

    farm = vaccination.farm
    currency = (farm.currency if farm else None) or 'ETB'
    source_key = f'vaccination-expense-{vaccination.pk}'
    tag = vaccination.cattle.tag_id if vaccination.cattle_id else '?'
    return _upsert_linked_expense(
        farm=farm,
        source_key=source_key,
        category=Transaction.Category.VET,
        amount=vaccination.cost,
        currency=currency,
        date=vaccination.administered_on,
        description=f'Vaccination: {vaccination.vaccine_name} — {tag}',
    )


def sync_treatment_expense(treatment):
    from finance.models import Transaction

    farm = treatment.farm
    currency = (farm.currency if farm else None) or 'ETB'
    source_key = f'treatment-expense-{treatment.pk}'
    tag = treatment.cattle.tag_id if treatment.cattle_id else '?'
    return _upsert_linked_expense(
        farm=farm,
        source_key=source_key,
        category=Transaction.Category.VET,
        amount=treatment.cost,
        currency=currency,
        date=treatment.start_date,
        description=f'Treatment: {treatment.diagnosis} — {tag}',
    )


def sync_feed_expense(feed):
    from finance.models import Transaction

    farm = feed.farm
    currency = (farm.currency if farm else None) or 'ETB'
    source_key = f'feed-expense-{feed.pk}'
    target = feed.cattle.tag_id if feed.cattle_id else 'herd'
    return _upsert_linked_expense(
        farm=farm,
        source_key=source_key,
        category=Transaction.Category.FEED,
        amount=feed.cost,
        currency=currency,
        date=feed.date,
        description=f'Feed: {feed.feed_type} ({feed.quantity} {feed.unit}) — {target}',
    )


def delete_linked_expense(farm, source_key):
    from finance.models import Transaction

    Transaction.objects.filter(farm=farm, source_key=source_key, is_auto=True).delete()


def milk_finance_snapshot(farm, days=30):
    from farm.models import Farm
    from finance.models import Transaction
    from milk.models import MilkRecord

    today = timezone.localdate()
    start = today - timedelta(days=days)
    price = farm.milk_price_per_liter if farm else Decimal('0')
    currency = farm.currency if farm else 'ETB'
    mode = farm.milk_income_mode if farm else Farm.MilkIncomeMode.ACCRUAL

    liters = (
        MilkRecord.objects.filter(farm=farm, date__gte=start, date__lte=today)
        .annotate(total=F('morning_liters') + F('evening_liters'))
        .aggregate(s=Sum('total'))['s']
        or Decimal('0')
    )
    auto_income = (
        Transaction.objects.filter(
            farm=farm,
            date__gte=start,
            date__lte=today,
            type=Transaction.Type.INCOME,
            category=Transaction.Category.MILK_PRODUCTION,
            is_auto=True,
        ).aggregate(s=Sum('amount'))['s']
        or Decimal('0')
    )
    cash_sales = (
        Transaction.objects.filter(
            farm=farm,
            date__gte=start,
            date__lte=today,
            type=Transaction.Type.INCOME,
            category=Transaction.Category.MILK_SALE,
        ).aggregate(s=Sum('amount'))['s']
        or Decimal('0')
    )
    today_liters = (
        MilkRecord.objects.filter(farm=farm, date=today)
        .annotate(total=F('morning_liters') + F('evening_liters'))
        .aggregate(s=Sum('total'))['s']
        or Decimal('0')
    )
    valued = (Decimal(liters) * Decimal(price or 0)).quantize(Decimal('0.01'))
    return {
        'price_per_liter': price,
        'currency': currency,
        'mode': mode,
        'auto_enabled': bool(farm.books_production_income) if farm else False,
        'liters': liters,
        'valued_income': valued,
        'auto_income_booked': auto_income,
        'cash_sales': cash_sales,
        'period_milk_income': auto_income + cash_sales,
        'today_liters': today_liters,
        'today_milk_value': (Decimal(today_liters) * Decimal(price or 0)).quantize(
            Decimal('0.01')
        ),
    }


def finance_period_totals(farm, days=30):
    from farm.models import Farm
    from finance.models import Transaction

    today = timezone.localdate()
    start = today - timedelta(days=days)
    mode = farm.milk_income_mode if farm else Farm.MilkIncomeMode.ACCRUAL
    qs = Transaction.objects.filter(farm=farm, date__gte=start, date__lte=today)

    income_qs = qs.filter(type=Transaction.Type.INCOME)
    if mode == Farm.MilkIncomeMode.ACCRUAL:
        income_qs = income_qs.exclude(category=Transaction.Category.MILK_SALE)
    else:
        income_qs = income_qs.exclude(category=Transaction.Category.MILK_PRODUCTION)

    income = income_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0')
    expense = (
        qs.filter(type=Transaction.Type.EXPENSE).aggregate(s=Sum('amount'))['s']
        or Decimal('0')
    )
    return {
        'start': start,
        'end': today,
        'income': income,
        'expense': expense,
        'profit': income - expense,
        'mode': mode,
    }

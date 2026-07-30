"""Milk production helpers and missed-record alerts."""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import F, Sum
from django.utils import timezone


def _missed_milk_dates(today=None, now=None):
    """
    Days that should already have a milk record.

    - Yesterday is always checked (catches overnight / morning cron).
    - Today is checked only after MISSED_MILK_ALERT_AFTER_HOUR so morning
      runs do not flag cows before evening milking is due.
    """
    today = today or timezone.localdate()
    now = now or timezone.localtime()
    after_hour = int(getattr(settings, 'MISSED_MILK_ALERT_AFTER_HOUR', 18))
    dates = [today - timedelta(days=1)]
    if now.hour >= after_hour:
        dates.append(today)
    return dates


def generate_missed_milk_alerts(farm=None):
    """
    Alert for actively milking cattle with no milk record for expected days.
    Returns number of new alerts created.
    """
    from alerts.models import Alert
    from alerts.services import create_alert_if_new
    from cattle.models import Cattle
    from farm.models import Farm

    from .models import MilkRecord

    farms = [farm] if farm is not None else list(Farm.objects.all())
    created = 0
    check_dates = _missed_milk_dates()

    for f in farms:
        candidates = list(
            Cattle.objects.filter(
                farm=f,
                sex=Cattle.Sex.FEMALE,
                status=Cattle.Status.ACTIVE,
            ).select_related('farm')
        )
        milking = []
        stage_labels = {}
        for c in candidates:
            info = c.lactation_info()
            if info.get('stage') in ('FRESH', 'PEAK', 'MID', 'LATE'):
                milking.append(c)
                stage_labels[c.id] = info.get('stage_label', 'lactating')
        if not milking:
            continue

        milking_ids = [c.id for c in milking]
        for target_date in check_dates:
            recorded_ids = set(
                MilkRecord.objects.filter(
                    farm=f,
                    date=target_date,
                    cattle_id__in=milking_ids,
                ).values_list('cattle_id', flat=True)
            )
            for cow in milking:
                if target_date < cow.registered_on:
                    continue
                if cow.id in recorded_ids:
                    continue
                label = 'today' if target_date == timezone.localdate() else target_date.isoformat()
                _, was_created = create_alert_if_new(
                    category=Alert.Category.MILK,
                    severity=Alert.Severity.WARNING,
                    title=f'Missing milk record: {cow.tag_id}',
                    message=(
                        f'{cow.tag_id} is in active milking '
                        f'({stage_labels.get(cow.id, "lactating")}) '
                        f'but has no milk record for {label}.'
                    ),
                    cattle=cow,
                    farm=f,
                    dedupe_key=f'milk-missed-{cow.id}-{target_date.isoformat()}',
                )
                if was_created:
                    created += 1

    return created


def clear_missed_milk_alert(record):
    """Mark the missed-milk alert resolved once a record is logged for that day."""
    from alerts.models import Alert

    key = f'milk-missed-{record.cattle_id}-{record.date.isoformat()}'
    Alert.objects.filter(farm_id=record.farm_id, dedupe_key=key, is_read=False).update(
        is_read=True,
        acknowledged_at=timezone.now(),
    )


def estimated_dry_off_date(cattle, today=None):
    """Next estimated dry-off from pregnancy ECD or lactation target."""
    today = today or timezone.localdate()
    dry_days = cattle.DRY_PERIOD_DAYS
    target = cattle.LACTATION_TARGET_DAYS

    pregnancy = cattle.active_pregnancy()
    if pregnancy and pregnancy.expected_calving_date:
        return pregnancy.expected_calving_date - timedelta(days=dry_days)

    last_calving = cattle.last_calving_date()
    if last_calving:
        return last_calving + timedelta(days=target - dry_days)
    return None


def _average_daily(records_qs):
    annotated = records_qs.annotate(total=F('morning_liters') + F('evening_liters'))
    count = annotated.count()
    liters = annotated.aggregate(liters=Sum('total'))['liters'] or Decimal('0')
    if not count:
        return 0.0, 0, float(liters)
    return float(liters) / count, count, float(liters)


def herd_milk_overview(farm):
    """
    Rows for the milk page table: milking / post-calving females.

    Columns: cattle number, last birth, average production, next dry-off, DIM.
    """
    from breeding.models import BirthRecord
    from cattle.models import Cattle

    from .models import MilkRecord

    today = timezone.localdate()
    cows = list(
        Cattle.objects.filter(
            farm=farm,
            sex=Cattle.Sex.FEMALE,
            status=Cattle.Status.ACTIVE,
        ).order_by('tag_id')
    )

    birth_dates = {}
    for row in (
        BirthRecord.objects.filter(pregnancy__cattle__farm=farm)
        .values('pregnancy__cattle_id', 'calving_date')
        .order_by('pregnancy__cattle_id', '-calving_date')
    ):
        cid = row['pregnancy__cattle_id']
        if cid not in birth_dates:
            birth_dates[cid] = row['calving_date']

    milk_cattle_ids = set(
        MilkRecord.objects.filter(farm=farm)
        .values_list('cattle_id', flat=True)
        .distinct()
    )

    rows = []
    for cow in cows:
        last_birth = birth_dates.get(cow.id)
        if last_birth is None and cow.id not in milk_cattle_ids:
            continue

        lactation = cow.lactation_info()
        if last_birth:
            cycle_qs = MilkRecord.objects.filter(cattle=cow, date__gte=last_birth)
        else:
            cycle_qs = MilkRecord.objects.filter(cattle=cow)

        avg_daily, record_days, cycle_liters = _average_daily(cycle_qs)
        if avg_daily == 0:
            summary = cow.milk_summary()
            avg_daily = float(summary.get('average_daily_30') or 0)

        dry_off = estimated_dry_off_date(cow, today=today)
        dim = lactation.get('days_in_milk')
        if dim is None and last_birth:
            dim = (today - last_birth).days

        rows.append(
            {
                'cattle_id': cow.id,
                'cattle_number': cow.tag_id,
                'name': cow.name or '',
                'last_birth_date': last_birth.isoformat() if last_birth else None,
                'average_milk_production': round(avg_daily, 2),
                'next_estimated_dry_off': dry_off.isoformat() if dry_off else None,
                'milked_days_current_calving': dim,
                'lactation_stage': lactation.get('stage'),
                'lactation_stage_label': lactation.get('stage_label'),
                'is_actively_milking': cow.is_actively_milking,
                'cycle_total_liters': round(cycle_liters, 2),
                'cycle_record_days': record_days,
            }
        )

    return {'count': len(rows), 'results': rows}


def cattle_milk_history_by_cycle(cattle):
    """
    Milk records for one cow, grouped by calving cycle.
    Current (latest) calving cycle is first.
    """
    from breeding.models import BirthRecord

    from .models import MilkRecord
    from .serializers import MilkRecordSerializer

    today = timezone.localdate()
    births = list(
        BirthRecord.objects.filter(pregnancy__cattle=cattle)
        .select_related('pregnancy', 'calf')
        .order_by('-calving_date')
    )
    all_records = list(
        MilkRecord.objects.filter(cattle=cattle)
        .select_related('cattle', 'recorded_by')
        .order_by('-date')
    )

    cycles = []
    for index, birth in enumerate(births):
        start = birth.calving_date
        if index == 0:
            end = today
            is_current = True
        else:
            newer = births[index - 1].calving_date
            end = newer - timedelta(days=1)
            is_current = False

        cycle_records = [r for r in all_records if start <= r.date <= end]
        liters = sum((r.morning_liters or 0) + (r.evening_liters or 0) for r in cycle_records)
        days = len(cycle_records)
        avg = float(liters) / days if days else 0.0
        dry_off = start + timedelta(
            days=cattle.LACTATION_TARGET_DAYS - cattle.DRY_PERIOD_DAYS
        )

        cycles.append(
            {
                'cycle_index': len(births) - index,
                'is_current': is_current,
                'calving_date': start.isoformat(),
                'cycle_end': end.isoformat(),
                'birth_id': birth.id,
                'calf_tag_id': birth.calf_tag_id
                or (birth.calf.tag_id if birth.calf_id else ''),
                'days_in_milk': (min(end, today) - start).days,
                'estimated_dry_off': dry_off.isoformat(),
                'record_count': days,
                'total_liters': float(liters),
                'average_daily': round(avg, 2),
                'label': (
                    f'Current calving · {start.isoformat()}'
                    if is_current
                    else f'Calving {len(births) - index} · {start.isoformat()}'
                ),
                'records': MilkRecordSerializer(cycle_records, many=True).data,
            }
        )

    if births:
        earliest = births[-1].calving_date
        prior = [r for r in all_records if r.date < earliest]
    else:
        prior = list(all_records)
        earliest = None

    if prior:
        liters = sum((r.morning_liters or 0) + (r.evening_liters or 0) for r in prior)
        days = len(prior)
        cycles.append(
            {
                'cycle_index': None,
                'is_current': not births,
                'calving_date': None,
                'cycle_end': (
                    (earliest - timedelta(days=1)).isoformat()
                    if earliest
                    else today.isoformat()
                ),
                'birth_id': None,
                'calf_tag_id': '',
                'days_in_milk': None,
                'estimated_dry_off': None,
                'record_count': days,
                'total_liters': float(liters),
                'average_daily': round(float(liters) / days, 2) if days else 0.0,
                'label': 'Before recorded calvings' if births else 'All milk records',
                'records': MilkRecordSerializer(prior, many=True).data,
            }
        )

    lactation = cattle.lactation_info()
    dry_off = estimated_dry_off_date(cattle, today=today)
    current_avg = cycles[0]['average_daily'] if cycles else 0.0

    return {
        'cattle_id': cattle.id,
        'cattle_number': cattle.tag_id,
        'name': cattle.name or '',
        'last_birth_date': lactation.get('last_calving_date'),
        'average_milk_production': current_avg,
        'next_estimated_dry_off': dry_off.isoformat() if dry_off else None,
        'milked_days_current_calving': lactation.get('days_in_milk'),
        'lactation_stage': lactation.get('stage'),
        'lactation_stage_label': lactation.get('stage_label'),
        'is_actively_milking': cattle.is_actively_milking,
        'cycles': cycles,
    }

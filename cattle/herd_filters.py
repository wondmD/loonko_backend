"""Herd list filters: calf / heifer / cow + reproductive status chips."""

from datetime import timedelta

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from breeding.models import BirthRecord, Pregnancy
from husbandry.models import HusbandrySettings


def _settings():
    """Legacy no-arg — prefer _settings_for_queryset."""
    return HusbandrySettings()


def _settings_for_queryset(queryset):
    farm_id = queryset.values_list('farm_id', flat=True).first()
    if farm_id:
        from farm.models import Farm

        return HusbandrySettings.load(Farm.objects.get(pk=farm_id))
    return HusbandrySettings()


def annotate_herd_flags(queryset):
    """Annotate queryset with has_calved + pregnancy helpers for filtering."""
    if 'has_calved' in queryset.query.annotations:
        return queryset
    has_calved = BirthRecord.objects.filter(pregnancy__cattle_id=OuterRef('pk'))
    pregnant = Pregnancy.objects.filter(
        cattle_id=OuterRef('pk'),
        status=Pregnancy.Status.PREGNANT,
    )
    ecd = (
        Pregnancy.objects.filter(
            cattle_id=OuterRef('pk'),
            status=Pregnancy.Status.PREGNANT,
            expected_calving_date__isnull=False,
        )
        .order_by('-expected_calving_date')
        .values('expected_calving_date')[:1]
    )
    last_calving = (
        BirthRecord.objects.filter(pregnancy__cattle_id=OuterRef('pk'))
        .order_by('-calving_date')
        .values('calving_date')[:1]
    )
    return queryset.annotate(
        has_calved=Exists(has_calved),
        is_pregnant_flag=Exists(pregnant),
        expected_calving=Subquery(ecd),
        last_calving_annot=Subquery(last_calving),
    )


def apply_category_filter(queryset, category: str | None):
    """Filter by CALF | HEIFER | COW (female dairy classes)."""
    if not category or category.upper() in ('ALL', ''):
        return queryset
    category = category.upper().strip()
    settings = _settings_for_queryset(queryset)
    today = timezone.localdate()
    weaning_cutoff = today - timedelta(days=settings.weaning_days)

    qs = annotate_herd_flags(queryset)

    if category == 'COW':
        return qs.filter(has_calved=True)
    if category == 'CALF':
        return qs.filter(
            has_calved=False,
            date_of_birth__isnull=False,
            date_of_birth__gt=weaning_cutoff,
        )
    if category == 'HEIFER':
        return qs.filter(has_calved=False).filter(
            Q(date_of_birth__isnull=True) | Q(date_of_birth__lte=weaning_cutoff)
        )
    return queryset


def apply_herd_filter(queryset, herd_filter: str | None):
    """
    Secondary chips:
    pregnant, close_calving, close_dry_off, open, fresh,
    needs_breeding, dry, calving_overdue
    """
    if not herd_filter:
        return queryset
    key = herd_filter.lower().strip()
    settings = _settings_for_queryset(queryset)
    today = timezone.localdate()
    qs = annotate_herd_flags(queryset)

    if key == 'pregnant':
        return qs.filter(is_pregnant_flag=True)

    if key == 'close_calving':
        end = today + timedelta(days=settings.calving_prep_days + 7)
        return qs.filter(
            is_pregnant_flag=True,
            expected_calving__gte=today - timedelta(days=3),
            expected_calving__lte=end,
        )

    if key == 'close_dry_off':
        low = today + timedelta(days=settings.dry_period_days - 10)
        high = today + timedelta(days=settings.dry_period_days + 10)
        return qs.filter(
            is_pregnant_flag=True,
            expected_calving__gte=low,
            expected_calving__lte=high,
        )

    if key == 'open':
        return qs.filter(is_pregnant_flag=False, sex='FEMALE', status='ACTIVE')

    if key == 'fresh':
        since = today - timedelta(days=settings.fresh_monitor_days)
        return qs.filter(last_calving_annot__gte=since, last_calving_annot__lte=today)

    if key == 'dry':
        return qs.filter(
            is_pregnant_flag=True,
            expected_calving__gte=today,
            expected_calving__lte=today + timedelta(days=settings.dry_period_days),
        )

    if key == 'needs_breeding':
        vwp_cut = today - timedelta(days=settings.voluntary_waiting_days)
        first_breed_cut = today - timedelta(days=settings.first_breeding_age_days)
        return qs.filter(is_pregnant_flag=False, status='ACTIVE', sex='FEMALE').filter(
            Q(has_calved=True, last_calving_annot__lte=vwp_cut)
            | Q(
                has_calved=False,
                date_of_birth__isnull=False,
                date_of_birth__lte=first_breed_cut,
            )
        )

    if key == 'calving_overdue':
        return qs.filter(
            is_pregnant_flag=True,
            expected_calving__lt=today - timedelta(days=2),
        )

    return queryset


def herd_facet_counts(base_queryset):
    """Counts for tabs/chips."""
    settings = _settings_for_queryset(base_queryset)
    today = timezone.localdate()
    weaning_cutoff = today - timedelta(days=settings.weaning_days)
    qs = annotate_herd_flags(base_queryset.filter(status='ACTIVE'))

    cow = qs.filter(has_calved=True).count()
    calf = qs.filter(
        has_calved=False,
        date_of_birth__isnull=False,
        date_of_birth__gt=weaning_cutoff,
    ).count()
    heifer = qs.filter(has_calved=False).exclude(
        date_of_birth__isnull=False,
        date_of_birth__gt=weaning_cutoff,
    ).count()

    return {
        'categories': {
            'ALL': cow + calf + heifer,
            'CALF': calf,
            'HEIFER': heifer,
            'COW': cow,
        },
        'filters': {
            'pregnant': apply_herd_filter(qs, 'pregnant').count(),
            'close_calving': apply_herd_filter(qs, 'close_calving').count(),
            'close_dry_off': apply_herd_filter(qs, 'close_dry_off').count(),
            'open': apply_herd_filter(qs, 'open').count(),
            'fresh': apply_herd_filter(qs, 'fresh').count(),
            'dry': apply_herd_filter(qs, 'dry').count(),
            'needs_breeding': apply_herd_filter(qs, 'needs_breeding').count(),
            'calving_overdue': apply_herd_filter(qs, 'calving_overdue').count(),
        },
    }

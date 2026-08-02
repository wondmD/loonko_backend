"""
Female dairy classification + suggested husbandry date windows.

Uses age, last calving, and last insemination/breeding to decide
calf / heifer / cow and recommend day ranges for key events.
"""

from datetime import date, timedelta

from django.utils import timezone

from .models import HusbandrySettings


def get_settings(farm=None):
    if farm is None:
        return HusbandrySettings()
    return HusbandrySettings.load(farm)


def _iso(d):
    return d.isoformat() if d else None


def _window(
    *,
    key,
    title,
    start,
    end,
    ideal=None,
    description='',
    today=None,
    registered_on=None,
):
    today = today or timezone.localdate()
    if start is None or end is None:
        return {
            'key': key,
            'title': title,
            'start': None,
            'end': None,
            'ideal': None,
            'status': 'N/A',
            'days_until_start': None,
            'days_until_end': None,
            'severity': None,
            'message': 'Not enough data to estimate this window.',
            'description': description,
        }

    if end < start:
        end = start

    ideal = ideal or start
    if ideal < start:
        ideal = start
    if ideal > end:
        ideal = end

    # Milestones fully before registration are out of scope for this herd.
    if registered_on is not None and end < registered_on:
        return {
            'key': key,
            'title': title,
            'start': _iso(start),
            'end': _iso(end),
            'ideal': _iso(ideal),
            'status': 'N/A',
            'days_until_start': (start - today).days,
            'days_until_end': (end - today).days,
            'severity': 'INFO',
            'message': 'Before this animal was registered — not tracked as overdue.',
            'description': description,
        }

    days_start = (start - today).days
    days_end = (end - today).days

    if today > end:
        status = 'OVERDUE'
        severity = 'CRITICAL' if days_end < -7 else 'WARNING'
        message = f'Window ended {abs(days_end)} day(s) ago ({_iso(end)}).'
    elif start <= today <= end:
        status = 'ACTIVE'
        severity = 'WARNING' if days_end <= 3 else 'INFO'
        message = f'In window now — closes in {days_end} day(s) ({_iso(end)}).'
    else:
        status = 'UPCOMING'
        severity = 'INFO'
        message = f'Opens in {days_start} day(s) ({_iso(start)} → {_iso(end)}).'

    return {
        'key': key,
        'title': title,
        'start': _iso(start),
        'end': _iso(end),
        'ideal': _iso(ideal),
        'status': status,
        'days_until_start': days_start,
        'days_until_end': days_end,
        'severity': severity,
        'message': message,
        'description': description,
    }


def classify_animal(cattle):
    """
    Auto-detect CALF / HEIFER / COW from age + last calving.
    Also returns reproductive sub-stage for UI.
    """
    today = timezone.localdate()
    settings = get_settings(cattle.farm)
    age = cattle.age_days
    last_calving = cattle.last_calving_date() if cattle.sex == cattle.Sex.FEMALE else None
    last_breeding = (
        cattle.last_breeding_event() if cattle.sex == cattle.Sex.FEMALE else None
    )
    last_ai = last_breeding.mating_date if last_breeding else None
    pregnancy = cattle.active_pregnancy() if cattle.sex == cattle.Sex.FEMALE else None
    open_preg = None
    if cattle.sex == cattle.Sex.FEMALE:
        open_preg = (
            cattle.pregnancies.filter(status='OPEN')
            .order_by('-created_at')
            .first()
        )

    base = {
        'age_days': age,
        'age_months': round(age / 30.4, 1) if age is not None else None,
        'last_calving_date': _iso(last_calving),
        'last_insemination_date': _iso(last_ai),
        'is_pregnant': bool(pregnancy),
        'awaiting_pregnancy_check': bool(open_preg and not pregnancy),
        'focus': cattle.status == cattle.Status.ACTIVE,
    }

    if cattle.sex != cattle.Sex.FEMALE:
        return {
            **base,
            'category': 'MALE',
            'category_label': 'Bull / male',
            'code': 'MALE',
            'label': 'Bull / male',
            'basis': 'Sex is male — dairy husbandry schedule is female-focused.',
            'focus': False,
        }

    if cattle.status != cattle.Status.ACTIVE:
        return {
            **base,
            'category': 'INACTIVE',
            'category_label': cattle.get_status_display(),
            'code': cattle.status,
            'label': cattle.get_status_display(),
            'basis': f'Status is {cattle.status}.',
            'focus': False,
        }

    # --- Primary class: calf / heifer / cow ---
    cow_maturity_days = settings.first_breeding_age_days + settings.gestation_days
    if last_calving is not None:
        category = 'COW'
        category_label = 'Cow'
        basis_parts = [f'Last calved {_iso(last_calving)}']
    elif age is not None and age >= cow_maturity_days:
        category = 'COW'
        category_label = 'Cow'
        basis_parts = [
            f'Age {age} days (~{round(age / 365, 1)} yrs, mature cow)',
            'never calved in system',
        ]
    elif age is not None and age < settings.weaning_days:
        category = 'CALF'
        category_label = 'Calf'
        basis_parts = [
            f'Age {age} days (< {settings.weaning_days}-day weaning threshold)',
            'never calved',
        ]
    else:
        category = 'HEIFER'
        category_label = 'Heifer'
        if age is not None:
            basis_parts = [f'Age {age} days', 'never calved']
        else:
            basis_parts = ['Never calved (no DOB — treated as heifer)']

    if last_ai:
        basis_parts.append(f'last AI/service {_iso(last_ai)}')

    # --- Reproductive / rearing sub-stage ---
    code = category
    label = category_label

    if pregnancy and pregnancy.status == 'PREGNANT':
        ecd = pregnancy.expected_calving_date
        if ecd and (ecd - today).days <= settings.dry_period_days:
            code = 'DRY'
            label = (
                'Dry heifer (pre-calving)'
                if category == 'HEIFER'
                else 'Dry cow (pre-calving)'
            )
        else:
            code = 'PREGNANT'
            label = f'Pregnant {category_label.lower()}'
    elif category == 'CALF':
        code, label = 'CALF', 'Heifer calf'
    elif category == 'HEIFER':
        if age is not None and age < settings.first_breeding_age_days:
            code, label = 'GROWING_HEIFER', 'Growing heifer'
        elif open_preg:
            code, label = 'BRED_HEIFER', 'Bred heifer (awaiting check)'
        else:
            code, label = 'BREEDING_HEIFER', 'Breeding heifer'
    else:  # COW
        if open_preg:
            code, label = 'BRED_COW', 'Bred cow (awaiting check)'
        elif last_calving is None:
            code, label = 'OPEN_COW', 'Mature cow (open)'
        else:
            dim = (today - last_calving).days
            if dim <= settings.fresh_monitor_days:
                code, label = 'FRESH', 'Fresh cow'
            else:
                milking_end = settings.lactation_target_days - settings.dry_period_days
                if dim > milking_end:
                    code, label = 'LATE_OPEN', 'Late-lactation open cow'
                else:
                    code, label = 'LACTATING', 'Lactating cow'

    return {
        **base,
        'category': category,
        'category_label': category_label,
        'code': code,
        'label': label,
        'basis': '; '.join(basis_parts) + '.',
        'focus': True,
    }


def suggested_windows(cattle):
    """Suggested day ranges for husbandry milestones."""
    today = timezone.localdate()
    settings = get_settings(cattle.farm)
    stage = classify_animal(cattle)
    windows = []
    registered_on = cattle.registered_on

    if cattle.sex != cattle.Sex.FEMALE or cattle.status != cattle.Status.ACTIVE:
        return {
            'animal_class': stage,
            'settings_used': _settings_snapshot(settings),
            'windows': [],
            'warnings': [],
        }

    age = cattle.age_days
    last_calving = cattle.last_calving_date()
    last_breeding = cattle.last_breeding_event()
    last_ai = last_breeding.mating_date if last_breeding else None
    pregnancy = cattle.active_pregnancy()
    open_preg = (
        cattle.pregnancies.filter(status='OPEN').order_by('-created_at').first()
    )

    def win(**kwargs):
        kwargs.setdefault('today', today)
        kwargs.setdefault('registered_on', registered_on)
        return _window(**kwargs)

    # Calf weaning
    if stage['category'] == 'CALF' and cattle.date_of_birth:
        wean = cattle.date_of_birth + timedelta(days=settings.weaning_days)
        windows.append(
            win(
                key='WEANING',
                title='Weaning window',
                start=wean - timedelta(days=7),
                end=wean + timedelta(days=14),
                ideal=wean,
                description=f'Target ~{settings.weaning_days} days of age.',
            )
        )

    # First / next insemination
    if not pregnancy:
        if stage['category'] == 'HEIFER' and cattle.date_of_birth:
            first = cattle.date_of_birth + timedelta(
                days=settings.first_breeding_age_days
            )
            # Only track first AI from registration forward
            first = max(first, registered_on)
            windows.append(
                win(
                    key='FIRST_INSEMINATION',
                    title='First insemination window',
                    start=first,
                    end=first + timedelta(days=settings.estrous_cycle_days * 2),
                    ideal=first,
                    description=(
                        f'Heifers typically eligible ~{settings.first_breeding_age_days} '
                        f'days of age (~{round(settings.first_breeding_age_days / 30.4)} months).'
                    ),
                )
            )
        elif last_calving:
            vwp_end = last_calving + timedelta(days=settings.voluntary_waiting_days)
            if last_ai and last_ai >= max(last_calving, registered_on):
                # Return heat after last service recorded on the system
                next_heat = last_ai + timedelta(days=settings.estrous_cycle_days)
                while next_heat < today - timedelta(days=settings.estrous_cycle_days):
                    next_heat += timedelta(days=settings.estrous_cycle_days)
                start = max(next_heat - timedelta(days=2), vwp_end, registered_on)
            else:
                # Past VWP before registration → start heat watch from registration day
                start = max(vwp_end, registered_on)
            if start < today:
                start = today
            windows.append(
                win(
                    key='INSEMINATION',
                    title='Suggested insemination window',
                    start=start,
                    end=start + timedelta(days=settings.heat_watch_days),
                    ideal=start,
                    description=(
                        f'After {settings.voluntary_waiting_days}-day VWP; '
                        f'~{settings.estrous_cycle_days}-day heat cycle.'
                    ),
                )
            )
        elif stage['category'] == 'COW':
            start = max(today, registered_on)
            windows.append(
                win(
                    key='INSEMINATION',
                    title='Suggested insemination window',
                    start=start,
                    end=start + timedelta(days=settings.heat_watch_days),
                    ideal=start,
                    description=(
                        'Mature open cow: observe heat cycles '
                        f'(~{settings.estrous_cycle_days} days) and schedule breeding / AI.'
                    ),
                )
            )
        elif stage['category'] == 'HEIFER':
            windows.append(
                win(
                    key='INSEMINATION',
                    title='Suggested insemination window',
                    start=today,
                    end=today + timedelta(days=settings.estrous_cycle_days),
                    ideal=today,
                    description='Open heifer — breed on confirmed heat.',
                )
            )

    # Pregnancy check after last AI (only if AI was on/after registration)
    if last_ai and last_ai >= registered_on and not pregnancy:
        check = last_ai + timedelta(days=settings.pregnancy_check_days)
        windows.append(
            win(
                key='PREGNANCY_CHECK',
                title='Pregnancy checkup window',
                start=check - timedelta(days=5),
                end=check + timedelta(days=10),
                ideal=check,
                description=(
                    f'Diagnose ~{settings.pregnancy_check_days} days after '
                    f'AI/service on {_iso(last_ai)}.'
                ),
            )
        )

    # Pregnant: dry-off, calving prep, calving
    ecd = None
    if pregnancy and pregnancy.expected_calving_date:
        ecd = pregnancy.expected_calving_date
    elif open_preg and open_preg.expected_calving_date:
        ecd = open_preg.expected_calving_date
    elif last_ai and last_ai >= registered_on:
        ecd = last_ai + timedelta(days=settings.gestation_days)

    if ecd and (pregnancy or open_preg or (last_ai and last_ai >= registered_on)):
        dry = ecd - timedelta(days=settings.dry_period_days)
        windows.append(
            win(
                key='DRY_OFF',
                title='Suggested dry-off window',
                start=dry - timedelta(days=7),
                end=dry + timedelta(days=7),
                ideal=dry,
                description=(
                    f'~{settings.dry_period_days} days before expected calving '
                    f'({_iso(ecd)}).'
                ),
            )
        )
        prep = ecd - timedelta(days=settings.calving_prep_days)
        windows.append(
            win(
                key='CALVING_PREP',
                title='Calving preparation window',
                start=prep,
                end=ecd,
                ideal=prep,
                description='Move to calving pen and monitor closely.',
            )
        )
        windows.append(
            win(
                key='CALVING',
                title='Expected calving window',
                start=ecd - timedelta(days=7),
                end=ecd + timedelta(days=10),
                ideal=ecd,
                description=(
                    f'Gestation ~{settings.gestation_days} days from breeding/AI.'
                ),
            )
        )

    # Projected dry-off from lactation if open cow with calving history
    if last_calving and not pregnancy and not open_preg:
        proj_dry = last_calving + timedelta(
            days=settings.lactation_target_days - settings.dry_period_days
        )
        # Only if not already covered by pregnant dry-off above
        if not any(w['key'] == 'DRY_OFF' for w in windows):
            windows.append(
                win(
                    key='DRY_OFF_PROJECTED',
                    title='Projected dry-off (lactation)',
                    start=proj_dry - timedelta(days=10),
                    end=proj_dry + timedelta(days=14),
                    ideal=proj_dry,
                    description=(
                        f'Based on {settings.lactation_target_days}-day lactation '
                        'target if still open.'
                    ),
                )
            )

    # Fresh cow monitor after calving (only while still within window after registration)
    if last_calving:
        fresh_end = last_calving + timedelta(days=settings.fresh_monitor_days)
        windows.append(
            win(
                key='FRESH_MONITOR',
                title='Fresh-cow checkup window',
                start=last_calving,
                end=fresh_end,
                ideal=last_calving + timedelta(days=3),
                description=(
                    f'Daily monitoring for {settings.fresh_monitor_days} days '
                    'post-calving.'
                ),
            )
        )

    # Drop milestones that fully predate registration
    windows = [w for w in windows if w.get('status') != 'N/A']

    # Sort: overdue first, then active, then by start
    order = {'OVERDUE': 0, 'ACTIVE': 1, 'UPCOMING': 2, 'N/A': 3}
    windows.sort(key=lambda w: (order.get(w['status'], 9), w['start'] or '9999'))

    warnings = evaluate_risks(cattle, stage=stage, windows=windows, today=today)

    return {
        'animal_class': stage,
        'settings_used': _settings_snapshot(settings),
        'windows': windows,
        'warnings': warnings,
    }


def _settings_snapshot(settings):
    return {
        'gestation_days': settings.gestation_days,
        'voluntary_waiting_days': settings.voluntary_waiting_days,
        'dry_period_days': settings.dry_period_days,
        'lactation_target_days': settings.lactation_target_days,
        'estrous_cycle_days': settings.estrous_cycle_days,
        'pregnancy_check_days': settings.pregnancy_check_days,
        'weaning_days': settings.weaning_days,
        'first_breeding_age_days': settings.first_breeding_age_days,
        'fresh_monitor_days': settings.fresh_monitor_days,
        'calving_prep_days': settings.calving_prep_days,
        'heat_watch_days': settings.heat_watch_days,
    }


def evaluate_risks(cattle, stage=None, windows=None, today=None):
    """Detect wrong / late husbandry situations for alerts + UI warnings."""
    today = today or timezone.localdate()
    settings = get_settings(cattle.farm)
    stage = stage or classify_animal(cattle)
    windows = windows if windows is not None else suggested_windows(cattle)['windows']
    warnings = []
    registered_on = cattle.registered_on

    if cattle.sex != cattle.Sex.FEMALE or cattle.status != cattle.Status.ACTIVE:
        return warnings

    def add(code, title, message, severity='WARNING'):
        warnings.append(
            {
                'code': code,
                'title': title,
                'message': message,
                'severity': severity,
            }
        )

    def _parse_date(value):
        if value is None:
            return None
        if hasattr(value, 'year'):
            return value
        try:
            from datetime import date as date_cls

            return date_cls.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    for w in windows:
        if w['status'] == 'OVERDUE' and w['key'] in (
            'PREGNANCY_CHECK',
            'CALVING',
            'DRY_OFF',
            'INSEMINATION',
            'FIRST_INSEMINATION',
            'WEANING',
            'FRESH_MONITOR',
        ):
            # Skip windows that already ended before the animal was registered
            window_end = _parse_date(w.get('end'))
            if window_end is not None and window_end < registered_on:
                continue
            severity = 'CRITICAL' if w['key'] in ('CALVING', 'PREGNANCY_CHECK') else 'WARNING'
            add(
                f'OVERDUE_{w["key"]}',
                f'Overdue: {w["title"]}',
                w['message'],
                severity=severity,
            )

    # Calved expected but no birth (only if ECD was on/after registration)
    pregnancy = cattle.active_pregnancy()
    if pregnancy and pregnancy.expected_calving_date:
        ecd = pregnancy.expected_calving_date
        if ecd >= registered_on and ecd < today - timedelta(days=3):
            add(
                'CALVING_PAST_DUE',
                'Expected calving passed',
                (
                    f'{cattle.tag_id} was due around {ecd} '
                    'but no birth record is logged.'
                ),
                severity='CRITICAL',
            )

    # Open too long — count open days only from registration onward
    last_calving = cattle.last_calving_date()
    last_breeding = cattle.last_breeding_event()
    if last_calving and not pregnancy:
        open_since = max(last_calving, registered_on)
        if (today - open_since).days > settings.voluntary_waiting_days + 45:
            recent_ai = (
                last_breeding
                and last_breeding.mating_date >= open_since
                and (today - last_breeding.mating_date).days < 40
            )
            if not recent_ai:
                add(
                    'OPEN_TOO_LONG',
                    'Open cow past breeding target',
                    (
                        f'{cattle.tag_id} has been open '
                        f'{(today - open_since).days} days since tracking started '
                        f'(VWP {settings.voluntary_waiting_days}d). '
                        'Consider heat detection / AI.'
                    ),
                    severity='WARNING',
                )

    # Heifer past breeding age never served — only if eligibility was after registration
    age = cattle.age_days
    if (
        stage['category'] == 'HEIFER'
        and age is not None
        and cattle.date_of_birth
        and age > settings.first_breeding_age_days + 60
        and not last_breeding
    ):
        first_breed_on = cattle.date_of_birth + timedelta(
            days=settings.first_breeding_age_days
        )
        if first_breed_on >= registered_on:
            add(
                'HEIFER_UNBRED',
                'Heifer past first-breeding age',
                (
                    f'{cattle.tag_id} is {age} days old and has no breeding/AI record '
                    f'(target ~{settings.first_breeding_age_days} days).'
                ),
                severity='WARNING',
            )

    # Missing DOB for young animal planning
    if not cattle.date_of_birth and stage['category'] in ('CALF', 'HEIFER'):
        add(
            'MISSING_DOB',
            'Date of birth missing',
            'Add DOB so calf/heifer age windows (weaning, first AI) are accurate.',
            severity='INFO',
        )

    return warnings


def publish_risk_alerts(cattle=None, farm=None):
    """Create Alert rows from evaluate_risks. Returns count created."""
    from alerts.models import Alert
    from alerts.services import create_alert_if_new
    from cattle.models import Cattle

    created = 0
    qs = Cattle.objects.filter(sex=Cattle.Sex.FEMALE, status=Cattle.Status.ACTIVE)
    if cattle is not None:
        qs = qs.filter(pk=cattle.pk)
    if farm is not None:
        qs = qs.filter(farm=farm)

    for cow in qs.iterator():
        plan = suggested_windows(cow)
        for warning in plan['warnings']:
            if warning['severity'] == 'INFO':
                continue
            severity = (
                Alert.Severity.CRITICAL
                if warning['severity'] == 'CRITICAL'
                else Alert.Severity.WARNING
            )
            category = Alert.Category.BREEDING
            if 'WEANING' in warning['code'] or 'FRESH' in warning['code']:
                category = Alert.Category.HEALTH
            _, was_created = create_alert_if_new(
                category=category,
                severity=severity,
                title=warning['title'],
                message=warning['message'],
                cattle=cow,
                farm=cow.farm,
                dedupe_key=f'risk-{cow.id}-{warning["code"]}-{timezone.localdate()}',
            )
            if was_created:
                created += 1
    return created

"""Female dairy cattle husbandry lifecycle engine."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import HusbandrySettings, HusbandryTask


def get_settings(farm=None):
    if farm is None:
        return HusbandrySettings()
    return HusbandrySettings.load(farm)


def life_stage(cattle):
    """Human-readable reproductive / rearing stage for females."""
    from .planning import classify_animal

    return classify_animal(cattle)


def _upsert_task(
    *,
    cattle,
    task_type,
    title,
    description,
    due_date,
    source_key,
    priority=HusbandryTask.Priority.NORMAL,
    related_breeding=None,
    related_pregnancy=None,
    active_keys=None,
):
    if due_date is None:
        return None

    # Do not schedule / revive tasks for milestones that were already past
    # before this animal was registered in Loonkoo.
    registered_on = getattr(cattle, 'registered_on', None)
    if registered_on is not None and due_date < registered_on:
        HusbandryTask.objects.filter(
            farm_id=cattle.farm_id,
            source_key=source_key,
            is_auto=True,
            status=HusbandryTask.Status.PENDING,
        ).update(status=HusbandryTask.Status.CANCELLED)
        return None

    if active_keys is not None:
        active_keys.add(source_key)

    task, created = HusbandryTask.objects.get_or_create(
        farm_id=cattle.farm_id,
        source_key=source_key,
        defaults={
            'cattle': cattle,
            'task_type': task_type,
            'title': title,
            'description': description,
            'due_date': due_date,
            'priority': priority,
            'is_auto': True,
            'related_breeding': related_breeding,
            'related_pregnancy': related_pregnancy,
            'status': HusbandryTask.Status.PENDING,
        },
    )
    if not created:
        # Refresh plan fields if still open; keep completed/skipped as-is
        if task.status in (
            HusbandryTask.Status.PENDING,
            HusbandryTask.Status.CANCELLED,
        ):
            task.cattle = cattle
            task.task_type = task_type
            task.title = title
            task.description = description
            task.due_date = due_date
            task.priority = priority
            task.related_breeding = related_breeding
            task.related_pregnancy = related_pregnancy
            task.status = HusbandryTask.Status.PENDING
            task.is_auto = True
            task.save()
    return task


@transaction.atomic
def sync_cattle_husbandry(cattle):
    """
    Rebuild open auto husbandry tasks for one animal.
    Focused on female dairy lifecycle; males get open auto tasks cancelled.
    """
    active_keys = set()
    settings = get_settings(cattle.farm)
    today = timezone.localdate()

    if cattle.sex != cattle.Sex.FEMALE or cattle.status != cattle.Status.ACTIVE:
        HusbandryTask.objects.filter(
            cattle=cattle,
            is_auto=True,
            status=HusbandryTask.Status.PENDING,
        ).update(status=HusbandryTask.Status.CANCELLED)
        return {'cancelled_non_female': True, 'tasks': 0}

    pregnancy = cattle.active_pregnancy()
    pending_pregnancy = (
        cattle.pregnancies.filter(status='OPEN')
        .order_by('-created_at')
        .first()
    )
    last_calving = cattle.last_calving_date()
    last_breeding = cattle.last_breeding_event()
    age = cattle.age_days
    awaiting_check = bool(pending_pregnancy and not pregnancy)

    # --- Calf / heifer rearing ---
    if cattle.date_of_birth and last_calving is None:
        wean_on = cattle.date_of_birth + timedelta(days=settings.weaning_days)
        if wean_on >= today - timedelta(days=30):
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.WEANING,
                title='Wean heifer calf',
                description=(
                    f'Target weaning ~{settings.weaning_days} days of age. '
                    'Confirm solid feed intake before weaning.'
                ),
                due_date=wean_on,
                source_key=f'wean-{cattle.id}-{cattle.date_of_birth.isoformat()}',
                priority=HusbandryTask.Priority.NORMAL,
                active_keys=active_keys,
            )

        first_breed = cattle.date_of_birth + timedelta(
            days=settings.first_breeding_age_days
        )
        if first_breed >= today - timedelta(days=14) and not last_breeding:
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.FIRST_BREEDING,
                title='First breeding eligibility',
                description=(
                    f'Heifer reaches typical breeding age '
                    f'(~{settings.first_breeding_age_days} days). '
                    'Confirm weight/condition before AI or service.'
                ),
                due_date=first_breed,
                source_key=f'first-breed-{cattle.id}',
                priority=HusbandryTask.Priority.HIGH,
                active_keys=active_keys,
            )

    # --- Open cow / heifer: breeding & heat (not while pregnant or awaiting check) ---
    if not pregnancy and not awaiting_check:
        if last_calving:
            vwp_end = last_calving + timedelta(days=settings.voluntary_waiting_days)
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.REBREEDING,
                title='End of voluntary waiting period',
                description=(
                    f'Rebreeding eligible {settings.voluntary_waiting_days} days '
                    'after calving. Start heat detection.'
                ),
                due_date=vwp_end,
                source_key=f'rebreed-vwp-{cattle.id}-{last_calving.isoformat()}',
                priority=HusbandryTask.Priority.HIGH,
                active_keys=active_keys,
            )
            earliest = max(vwp_end, today)
        elif age is not None and age >= settings.first_breeding_age_days:
            earliest = today
        elif cattle.date_of_birth:
            earliest = cattle.date_of_birth + timedelta(
                days=settings.first_breeding_age_days
            )
        else:
            earliest = today

        # Heat / breeding window if open and past eligibility
        if earliest <= today + timedelta(days=90):
            if last_breeding and last_breeding.mating_date >= (
                last_calving or cattle.date_of_birth or last_breeding.mating_date
            ):
                # After a recent mating without confirmed pregnancy: return heat
                next_heat = last_breeding.mating_date + timedelta(
                    days=settings.estrous_cycle_days
                )
                while next_heat < today:
                    next_heat += timedelta(days=settings.estrous_cycle_days)
                heat_start = next_heat
            else:
                heat_start = earliest if earliest >= today else today

            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.HEAT_WATCH,
                title='Heat detection window',
                description=(
                    f'Observe for estrus (~{settings.estrous_cycle_days}-day cycle). '
                    'Watch mounting, mucus, restlessness.'
                ),
                due_date=heat_start,
                source_key=f'heat-{cattle.id}-{heat_start.isoformat()}',
                priority=HusbandryTask.Priority.HIGH,
                related_breeding=last_breeding,
                active_keys=active_keys,
            )
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.BREEDING,
                title='Breeding / AI due',
                description='Inseminate or natural service when heat is confirmed.',
                due_date=heat_start,
                source_key=f'breed-{cattle.id}-{heat_start.isoformat()}',
                priority=HusbandryTask.Priority.HIGH,
                related_breeding=last_breeding,
                active_keys=active_keys,
            )

        # Lactation dry-off estimate for open milking cows
        if last_calving:
            dry_off = last_calving + timedelta(
                days=settings.lactation_target_days - settings.dry_period_days
            )
            if dry_off >= today - timedelta(days=7):
                _upsert_task(
                    cattle=cattle,
                    task_type=HusbandryTask.TaskType.DRY_OFF,
                    title='Projected dry-off',
                    description=(
                        f'Based on {settings.lactation_target_days}-day lactation '
                        f'and {settings.dry_period_days}-day dry period. '
                        'Adjust if pregnancy confirmed.'
                    ),
                    due_date=dry_off,
                    source_key=f'dry-open-{cattle.id}-{last_calving.isoformat()}',
                    priority=HusbandryTask.Priority.NORMAL,
                    active_keys=active_keys,
                )
                mid = last_calving + timedelta(days=100)
                if mid >= today - timedelta(days=7):
                    _upsert_task(
                        cattle=cattle,
                        task_type=HusbandryTask.TaskType.LACTATION_CHECK,
                        title='Peak / mid-lactation review',
                        description='Review milk yield, BCS, and breeding status.',
                        due_date=mid,
                        source_key=f'lact-check-{cattle.id}-{last_calving.isoformat()}',
                        priority=HusbandryTask.Priority.LOW,
                        active_keys=active_keys,
                    )

    # --- After breeding: pregnancy check (only for services after registration) ---
    if (
        last_breeding
        and last_breeding.mating_date >= cattle.registered_on
        and not pregnancy
    ):
        check_on = last_breeding.mating_date + timedelta(
            days=settings.pregnancy_check_days
        )
        linked = pending_pregnancy
        if linked and linked.breeding_event_id not in (None, last_breeding.id):
            linked = None
        if not linked:
            linked = (
                cattle.pregnancies.filter(breeding_event=last_breeding)
                .exclude(status='FAILED')
                .order_by('-created_at')
                .first()
            )
        already_resolved = linked and linked.status in ('CALVED', 'FAILED', 'PREGNANT')
        if not already_resolved:
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.PREGNANCY_CHECK,
                title='Pregnancy diagnosis',
                description=(
                    f'Check pregnancy ~{settings.pregnancy_check_days} days '
                    'after breeding (palpation / ultrasound).'
                ),
                due_date=check_on,
                source_key=f'preg-check-{last_breeding.id}',
                priority=HusbandryTask.Priority.HIGH,
                related_breeding=last_breeding,
                related_pregnancy=linked,
                active_keys=active_keys,
            )

    # --- Confirmed / active pregnancy ---
    if pregnancy and pregnancy.status == 'PREGNANT' and pregnancy.expected_calving_date:
        ecd = pregnancy.expected_calving_date
        dry_off = ecd - timedelta(days=settings.dry_period_days)
        prep = ecd - timedelta(days=settings.calving_prep_days)

        _upsert_task(
            cattle=cattle,
            task_type=HusbandryTask.TaskType.DRY_OFF,
            title='Dry-off before calving',
            description=(
                f'Dry off ~{settings.dry_period_days} days before expected calving. '
                'Dry-cow therapy / teat sealant as per protocol.'
            ),
            due_date=dry_off,
            source_key=f'dry-preg-{pregnancy.id}',
            priority=HusbandryTask.Priority.HIGH,
            related_pregnancy=pregnancy,
            active_keys=active_keys,
        )
        _upsert_task(
            cattle=cattle,
            task_type=HusbandryTask.TaskType.CALVING_PREP,
            title='Calving preparation',
            description=(
                'Move to calving area, check supplies, monitor closely.'
            ),
            due_date=prep,
            source_key=f'calve-prep-{pregnancy.id}',
            priority=HusbandryTask.Priority.CRITICAL,
            related_pregnancy=pregnancy,
            active_keys=active_keys,
        )
        _upsert_task(
            cattle=cattle,
            task_type=HusbandryTask.TaskType.CALVING,
            title='Expected calving',
            description='Expected calving date. Assist only if needed.',
            due_date=ecd,
            source_key=f'calving-{pregnancy.id}',
            priority=HusbandryTask.Priority.CRITICAL,
            related_pregnancy=pregnancy,
            active_keys=active_keys,
        )

    # --- Post-calving fresh cow ---
    if last_calving:
        fresh_end = last_calving + timedelta(days=settings.fresh_monitor_days)
        if fresh_end >= today - timedelta(days=7):
            _upsert_task(
                cattle=cattle,
                task_type=HusbandryTask.TaskType.FRESH_MONITOR,
                title='Fresh cow monitoring window',
                description=(
                    f'Daily check for {settings.fresh_monitor_days} days: '
                    'appetite, milk, metritis, ketosis, mastitis.'
                ),
                due_date=last_calving + timedelta(days=3),
                source_key=f'fresh-{cattle.id}-{last_calving.isoformat()}',
                priority=HusbandryTask.Priority.CRITICAL,
                active_keys=active_keys,
            )

    # --- Health: scheduled vaccinations ---
    from health.models import Vaccination

    for vac in Vaccination.objects.filter(
        cattle=cattle,
        next_due_on__isnull=False,
        next_due_on__gte=today - timedelta(days=14),
    ).order_by('next_due_on')[:10]:
        _upsert_task(
            cattle=cattle,
            task_type=HusbandryTask.TaskType.VACCINATION,
            title=f'Vaccination: {vac.vaccine_name}',
            description='Booster / next dose due from health records.',
            due_date=vac.next_due_on,
            source_key=f'vac-{vac.id}-{vac.next_due_on.isoformat()}',
            priority=HusbandryTask.Priority.HIGH,
            active_keys=active_keys,
        )

    # Cancel stale auto pending tasks not in the active plan
    stale = HusbandryTask.objects.filter(
        cattle=cattle,
        is_auto=True,
        status=HusbandryTask.Status.PENDING,
    ).exclude(source_key__in=active_keys)
    cancelled = stale.update(status=HusbandryTask.Status.CANCELLED)

    # Also drop any leftover pending auto tasks dated before registration
    pre_reg = HusbandryTask.objects.filter(
        cattle=cattle,
        is_auto=True,
        status=HusbandryTask.Status.PENDING,
        due_date__lt=cattle.registered_on,
    ).update(status=HusbandryTask.Status.CANCELLED)
    cancelled += pre_reg

    return {
        'cattle_id': cattle.id,
        'active_tasks': len(active_keys),
        'cancelled_stale': cancelled,
        'life_stage': life_stage(cattle),
    }


def sync_all_female_cattle(farm=None):
    from cattle.models import Cattle

    results = []
    qs = Cattle.objects.filter(sex=Cattle.Sex.FEMALE, status=Cattle.Status.ACTIVE)
    if farm is not None:
        qs = qs.filter(farm=farm)
    for cow in qs.iterator():
        results.append(sync_cattle_husbandry(cow))
    return results


def ensure_pregnancy_after_breeding(breeding_event):
    """
    After AI/natural service on a female: ensure an OPEN pregnancy draft
    with tentative expected calving for planning.
    """
    from breeding.models import Pregnancy

    dam = breeding_event.dam
    if dam.sex != dam.Sex.FEMALE:
        return None

    settings = get_settings(dam.farm)
    existing = (
        Pregnancy.objects.filter(cattle=dam, breeding_event=breeding_event)
        .order_by('-created_at')
        .first()
    )
    if existing:
        if not existing.expected_calving_date:
            existing.expected_calving_date = breeding_event.mating_date + timedelta(
                days=settings.gestation_days
            )
            existing.save(update_fields=['expected_calving_date', 'updated_at'])
        return existing

    # Avoid stacking if already confirmed pregnant from another event
    active = dam.active_pregnancy()
    if active and active.status == 'PREGNANT':
        return active

    return Pregnancy.objects.create(
        farm=dam.farm,
        cattle=dam,
        breeding_event=breeding_event,
        expected_calving_date=breeding_event.mating_date
        + timedelta(days=settings.gestation_days),
        status=Pregnancy.Status.OPEN,
        clinical_notes='Auto-created after breeding — confirm at pregnancy check.',
    )


def complete_tasks_for_event(*, cattle, task_types, related_breeding=None, related_pregnancy=None):
    qs = HusbandryTask.objects.filter(
        cattle=cattle,
        task_type__in=task_types,
        status=HusbandryTask.Status.PENDING,
    )
    if related_breeding is not None:
        qs = qs.filter(related_breeding=related_breeding)
    if related_pregnancy is not None:
        qs = qs.filter(related_pregnancy=related_pregnancy)
    now = timezone.now()
    return qs.update(
        status=HusbandryTask.Status.COMPLETED,
        completed_at=now,
    )


def generate_husbandry_alerts(farm=None):
    """Create alerts for due / overdue husbandry tasks. Returns count created."""
    from alerts.models import Alert
    from alerts.services import create_alert_if_new
    from farm.models import Farm

    created = 0
    farms = [farm] if farm is not None else list(Farm.objects.all())
    today = timezone.localdate()

    for f in farms:
        settings = get_settings(f)
        window_end = today + timedelta(days=settings.task_alert_lead_days)
        tasks = (
            HusbandryTask.objects.filter(
                farm=f,
                status=HusbandryTask.Status.PENDING,
                due_date__lte=window_end,
                cattle__sex='FEMALE',
                cattle__status='ACTIVE',
            )
            .select_related('cattle')
            .order_by('due_date')
        )

        for task in tasks:
            # Ignore milestones that were already due before registration
            if task.due_date < task.cattle.registered_on:
                continue
            days = (task.due_date - today).days
            if days < 0:
                severity = Alert.Severity.CRITICAL
                title = f'Overdue husbandry: {task.title}'
                when = f'{abs(days)} day(s) overdue'
            elif days == 0:
                severity = Alert.Severity.WARNING
                title = f'Due today: {task.title}'
                when = 'due today'
            else:
                severity = Alert.Severity.INFO
                title = f'Upcoming: {task.title}'
                when = f'due in {days} day(s)'

            category = Alert.Category.BREEDING
            if task.task_type in (
                HusbandryTask.TaskType.FRESH_MONITOR,
                HusbandryTask.TaskType.WEANING,
                HusbandryTask.TaskType.LACTATION_CHECK,
                HusbandryTask.TaskType.VACCINATION,
            ):
                category = Alert.Category.HEALTH

            _, was_created = create_alert_if_new(
                category=category,
                severity=severity,
                title=title,
                message=(
                    f'{task.cattle.tag_id}: {task.title} {when} ({task.due_date}). '
                    f'{task.description}'
                ),
                cattle=task.cattle,
                farm=f,
                dedupe_key=f'husbandry-{task.id}-{task.due_date}',
            )
            if was_created:
                created += 1

    from .planning import publish_risk_alerts

    created += publish_risk_alerts(farm=farm)
    return created

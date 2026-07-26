from django.utils import timezone

from .models import Alert


def create_alert_if_new(
    *,
    category,
    severity,
    title,
    message,
    cattle=None,
    user=None,
    farm=None,
    dedupe_key='',
):
    if farm is None and cattle is not None:
        farm = cattle.farm
    if farm is None:
        raise ValueError('farm is required to create an alert')

    if dedupe_key:
        existing = Alert.objects.filter(farm=farm, dedupe_key=dedupe_key).first()
        if existing:
            return existing, False
    alert = Alert.objects.create(
        farm=farm,
        category=category,
        severity=severity,
        title=title,
        message=message,
        cattle=cattle,
        user=user,
        dedupe_key=dedupe_key or '',
    )
    return alert, True


def generate_due_alerts(farm=None):
    """Create vaccination and calving due alerts. Returns count created."""
    from datetime import timedelta

    from django.conf import settings

    from breeding.models import Pregnancy
    from farm.models import Farm
    from health.models import Vaccination
    from husbandry.services import generate_husbandry_alerts, sync_all_female_cattle

    created = 0
    today = timezone.localdate()
    farms = [farm] if farm is not None else list(Farm.objects.all())

    vac_end = today + timedelta(days=settings.VACCINATION_DUE_DAYS)
    calving_end = today + timedelta(days=settings.CALVING_DUE_DAYS)

    for f in farms:
        for vac in Vaccination.objects.filter(
            farm=f,
            next_due_on__isnull=False,
            next_due_on__gte=today,
            next_due_on__lte=vac_end,
        ).select_related('cattle'):
            _, was_created = create_alert_if_new(
                category=Alert.Category.HEALTH,
                severity=Alert.Severity.WARNING,
                title=f'Vaccination due: {vac.vaccine_name}',
                message=(
                    f'{vac.cattle.tag_id} needs {vac.vaccine_name} by {vac.next_due_on}.'
                ),
                cattle=vac.cattle,
                farm=f,
                dedupe_key=f'vac-due-{vac.id}-{vac.next_due_on}',
            )
            if was_created:
                created += 1

        for preg in Pregnancy.objects.filter(
            farm=f,
            status=Pregnancy.Status.PREGNANT,
            expected_calving_date__isnull=False,
            expected_calving_date__gte=today,
            expected_calving_date__lte=calving_end,
        ).select_related('cattle'):
            _, was_created = create_alert_if_new(
                category=Alert.Category.BREEDING,
                severity=Alert.Severity.INFO,
                title=f'Calving approaching: {preg.cattle.tag_id}',
                message=(
                    f'{preg.cattle.tag_id} expected to calve around {preg.expected_calving_date}.'
                ),
                cattle=preg.cattle,
                farm=f,
                dedupe_key=f'calving-due-{preg.id}-{preg.expected_calving_date}',
            )
            if was_created:
                created += 1

        sync_all_female_cattle(farm=f)
        created += generate_husbandry_alerts(farm=f)

    return created

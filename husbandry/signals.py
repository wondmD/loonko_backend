"""
Cross-module sync: cattle husbandry schedules + alerts stay aligned when
milk, health, breeding, or finance records change.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver(post_save, sender='cattle.Cattle')
def cattle_saved_sync_husbandry(sender, instance, **kwargs):
    from .planning import publish_risk_alerts
    from .services import sync_cattle_husbandry

    sync_cattle_husbandry(instance)
    if instance.sex == instance.Sex.FEMALE and instance.status == instance.Status.ACTIVE:
        publish_risk_alerts(cattle=instance)


@receiver(post_save, sender='breeding.BreedingEvent')
def breeding_saved_sync_husbandry(sender, instance, created, **kwargs):
    from .models import HusbandryTask
    from .services import (
        complete_tasks_for_event,
        ensure_pregnancy_after_breeding,
        sync_cattle_husbandry,
    )

    if instance.dam.sex == instance.dam.Sex.FEMALE:
        ensure_pregnancy_after_breeding(instance)
        if created:
            complete_tasks_for_event(
                cattle=instance.dam,
                task_types=[
                    HusbandryTask.TaskType.HEAT_WATCH,
                    HusbandryTask.TaskType.BREEDING,
                    HusbandryTask.TaskType.FIRST_BREEDING,
                    HusbandryTask.TaskType.REBREEDING,
                ],
            )
        sync_cattle_husbandry(instance.dam)


@receiver(post_save, sender='breeding.Pregnancy')
def pregnancy_saved_sync_husbandry(sender, instance, **kwargs):
    from .models import HusbandryTask
    from .services import complete_tasks_for_event, sync_cattle_husbandry

    if instance.status == instance.Status.PREGNANT and instance.confirmed_on:
        complete_tasks_for_event(
            cattle=instance.cattle,
            task_types=[HusbandryTask.TaskType.PREGNANCY_CHECK],
            related_breeding=instance.breeding_event,
        )
    if instance.status in (instance.Status.FAILED, instance.Status.CALVED):
        HusbandryTask.objects.filter(
            related_pregnancy=instance,
            status=HusbandryTask.Status.PENDING,
            is_auto=True,
        ).exclude(
            task_type=HusbandryTask.TaskType.CALVING,
        ).update(status=HusbandryTask.Status.CANCELLED)

    sync_cattle_husbandry(instance.cattle)


@receiver(post_save, sender='breeding.BirthRecord')
def birth_saved_sync_husbandry(sender, instance, created, **kwargs):
    from .models import HusbandryTask
    from .services import complete_tasks_for_event, sync_cattle_husbandry

    dam = instance.pregnancy.cattle
    if created:
        complete_tasks_for_event(
            cattle=dam,
            task_types=[
                HusbandryTask.TaskType.CALVING,
                HusbandryTask.TaskType.CALVING_PREP,
                HusbandryTask.TaskType.DRY_OFF,
            ],
            related_pregnancy=instance.pregnancy,
        )
    sync_cattle_husbandry(dam)
    if instance.calf_id:
        sync_cattle_husbandry(instance.calf)


@receiver(post_save, sender='milk.MilkRecord')
def milk_saved_sync_modules(sender, instance, created, **kwargs):
    """Milk logs refresh lactation-aware husbandry and can complete fresh-cow checks."""
    from datetime import timedelta

    from .models import HusbandryTask
    from .services import complete_tasks_for_event, get_settings, sync_cattle_husbandry

    cattle = instance.cattle
    if cattle.sex != cattle.Sex.FEMALE:
        return

    sync_cattle_husbandry(cattle)

    last_calving = cattle.last_calving_date()
    if last_calving:
        settings = get_settings()
        fresh_end = last_calving + timedelta(days=settings.fresh_monitor_days)
        if instance.date >= fresh_end - timedelta(days=1):
            complete_tasks_for_event(
                cattle=cattle,
                task_types=[HusbandryTask.TaskType.FRESH_MONITOR],
            )

@receiver(post_delete, sender='milk.MilkRecord')
def milk_deleted_sync_modules(sender, instance, **kwargs):
    from .services import sync_cattle_husbandry

    if instance.cattle_id:
        sync_cattle_husbandry(instance.cattle)


@receiver(post_save, sender='health.Vaccination')
def vaccination_saved_sync_modules(sender, instance, created, **kwargs):
    from alerts.models import Alert
    from alerts.services import create_alert_if_new
    from django.utils import timezone

    from .models import HusbandryTask
    from .services import sync_cattle_husbandry

    cattle = instance.cattle
    if created:
        HusbandryTask.objects.filter(
            cattle=cattle,
            task_type=HusbandryTask.TaskType.VACCINATION,
            status=HusbandryTask.Status.PENDING,
            title__icontains=instance.vaccine_name,
        ).update(
            status=HusbandryTask.Status.COMPLETED,
            completed_at=timezone.now(),
        )

    sync_cattle_husbandry(cattle)

    if instance.next_due_on:
        today = timezone.localdate()
        days = (instance.next_due_on - today).days
        if 0 <= days <= 14:
            create_alert_if_new(
                category=Alert.Category.HEALTH,
                severity=Alert.Severity.WARNING if days <= 7 else Alert.Severity.INFO,
                title=f'Vaccination due: {instance.vaccine_name}',
                message=(
                    f'{cattle.tag_id} needs {instance.vaccine_name} '
                    f'by {instance.next_due_on}.'
                ),
                cattle=cattle,
                farm=cattle.farm,
                dedupe_key=f'vac-due-{instance.id}-{instance.next_due_on}',
            )


@receiver(post_save, sender='health.HealthRecord')
def health_record_saved_sync_modules(sender, instance, created, **kwargs):
    from alerts.models import Alert
    from alerts.services import create_alert_if_new

    from .services import sync_cattle_husbandry

    sync_cattle_husbandry(instance.cattle)

    if not created:
        return

    if instance.severity in (
        instance.Severity.HIGH,
        instance.Severity.CRITICAL,
    ):
        symptoms = ', '.join(instance.symptoms) if instance.symptoms else 'clinical signs'
        create_alert_if_new(
            category=Alert.Category.HEALTH,
            severity=(
                Alert.Severity.CRITICAL
                if instance.severity == instance.Severity.CRITICAL
                else Alert.Severity.WARNING
            ),
            title=f'Health alert: {instance.cattle.tag_id}',
            message=f'{instance.severity} severity — {symptoms}. {instance.notes}'.strip(),
            cattle=instance.cattle,
            farm=instance.cattle.farm,
            dedupe_key=f'health-{instance.id}',
        )


@receiver(post_save, sender='health.Treatment')
def treatment_saved_sync_modules(sender, instance, created, **kwargs):
    from alerts.models import Alert
    from alerts.services import create_alert_if_new

    from .services import sync_cattle_husbandry

    sync_cattle_husbandry(instance.cattle)
    if created:
        create_alert_if_new(
            category=Alert.Category.HEALTH,
            severity=Alert.Severity.INFO,
            title=f'Treatment started: {instance.cattle.tag_id}',
            message=(
                f'{instance.diagnosis}'
                + (f' — {instance.medication}' if instance.medication else '')
            ),
            cattle=instance.cattle,
            farm=instance.cattle.farm,
            dedupe_key=f'treatment-{instance.id}',
        )


@receiver(post_save, sender='finance.Transaction')
def finance_saved_sync_modules(sender, instance, created, **kwargs):
    """Milk-sale income linked to a milk record refreshes that cow's husbandry context."""
    if not instance.related_milk_record_id:
        return
    from .services import sync_cattle_husbandry

    milk = instance.related_milk_record
    if milk and milk.cattle_id:
        sync_cattle_husbandry(milk.cattle)


@receiver(post_save, sender='milk.FeedSchedule')
def feed_saved_sync_modules(sender, instance, **kwargs):
    if instance.cattle_id:
        from .services import sync_cattle_husbandry

        sync_cattle_husbandry(instance.cattle)

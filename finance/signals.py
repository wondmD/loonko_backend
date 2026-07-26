from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

_PRICING_FIELDS = frozenset(
    {'milk_price_per_liter', 'currency', 'auto_milk_income', 'milk_income_mode'}
)


@receiver(pre_save, sender='milk.MilkRecord')
def milk_record_capture_old_date(sender, instance, **kwargs):
    if not instance.pk:
        instance._milk_income_old_date = None
        return
    try:
        previous = sender.objects.only('date', 'farm_id').get(pk=instance.pk)
        instance._milk_income_old_date = previous.date
    except sender.DoesNotExist:
        instance._milk_income_old_date = None


@receiver(post_save, sender='milk.MilkRecord')
def milk_record_sync_income(sender, instance, **kwargs):
    from .services import sync_daily_milk_income, sync_milk_income_for_record

    if instance.farm_id is None and instance.cattle_id:
        instance.farm_id = instance.cattle.farm_id
    old_date = getattr(instance, '_milk_income_old_date', None)
    sync_milk_income_for_record(instance)
    if old_date and old_date != instance.date and instance.farm_id:
        sync_daily_milk_income(instance.farm, old_date)


@receiver(post_delete, sender='milk.MilkRecord')
def milk_record_deleted_sync_income(sender, instance, **kwargs):
    from .services import sync_daily_milk_income

    if instance.farm_id:
        sync_daily_milk_income(instance.farm, instance.date)


@receiver(post_save, sender='farm.Farm')
def farm_pricing_resync_income(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if not created and update_fields is not None:
        if not _PRICING_FIELDS.intersection(update_fields):
            return

    from .services import backfill_milk_income

    backfill_milk_income(farm=instance, days=90)


@receiver(post_save, sender='health.Vaccination')
def vaccination_sync_expense(sender, instance, **kwargs):
    from .services import sync_vaccination_expense

    if instance.farm_id is None and instance.cattle_id:
        instance.farm_id = instance.cattle.farm_id
    sync_vaccination_expense(instance)


@receiver(post_delete, sender='health.Vaccination')
def vaccination_deleted_expense(sender, instance, **kwargs):
    from .services import delete_linked_expense

    if instance.farm_id:
        delete_linked_expense(instance.farm, f'vaccination-expense-{instance.pk}')


@receiver(post_save, sender='health.Treatment')
def treatment_sync_expense(sender, instance, **kwargs):
    from .services import sync_treatment_expense

    if instance.farm_id is None and instance.cattle_id:
        instance.farm_id = instance.cattle.farm_id
    sync_treatment_expense(instance)


@receiver(post_delete, sender='health.Treatment')
def treatment_deleted_expense(sender, instance, **kwargs):
    from .services import delete_linked_expense

    if instance.farm_id:
        delete_linked_expense(instance.farm, f'treatment-expense-{instance.pk}')


@receiver(post_save, sender='milk.FeedSchedule')
def feed_sync_expense(sender, instance, **kwargs):
    from .services import sync_feed_expense

    sync_feed_expense(instance)


@receiver(post_delete, sender='milk.FeedSchedule')
def feed_deleted_expense(sender, instance, **kwargs):
    from .services import delete_linked_expense

    if instance.farm_id:
        delete_linked_expense(instance.farm, f'feed-expense-{instance.pk}')

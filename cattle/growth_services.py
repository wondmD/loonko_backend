from decimal import Decimal
from django.utils import timezone
from alerts.models import Alert
from alerts.services import create_alert_if_new
from .models import CattleGrowthLog


def log_cattle_growth(*, cattle, weight_kg=None, bcs=None, date=None, recorded_by=None, notes=''):
    """
    Log weight & BCS entry for a cow and evaluate energy balance risk thresholds.
    """
    farm = cattle.farm
    
    if date:
        if isinstance(date, str):
            from datetime import date as dt_date
            date = dt_date.fromisoformat(date)
    else:
        date = timezone.localdate()

    if weight_kg is not None:
        weight_kg = Decimal(str(weight_kg))
    if bcs is not None:
        bcs = Decimal(str(bcs))

    log = CattleGrowthLog.objects.create(
        farm=farm,
        cattle=cattle,
        date=date,
        weight_kg=weight_kg,
        bcs=bcs,
        notes=notes,
        recorded_by=recorded_by,
    )

    # BCS Risk Threshold Evaluations
    if bcs is not None:
        stage = cattle.lactation_info().get('stage')
        if bcs < Decimal('2.25'):
            create_alert_if_new(
                category=Alert.Category.HEALTH,
                severity=Alert.Severity.WARNING if bcs >= Decimal('2.00') else Alert.Severity.CRITICAL,
                title=f'Low BCS Alert: {cattle.tag_id}',
                message=(
                    f'{cattle.tag_id} ({cattle.name or "cow"}) has a dangerously low Body Condition Score '
                    f'({bcs}/5.00). Check feed intake and monitor for metabolic issues.'
                ),
                cattle=cattle,
                farm=farm,
                dedupe_key=f'bcs-low-{cattle.id}-{date.isoformat()}',
            )
        elif stage == 'DRY' and bcs > Decimal('4.00'):
            create_alert_if_new(
                category=Alert.Category.HEALTH,
                severity=Alert.Severity.WARNING,
                title=f'High Dry Cow BCS Alert: {cattle.tag_id}',
                message=(
                    f'{cattle.tag_id} is dry with a high BCS ({bcs}/5.00). High BCS increases risk '
                    'for fat cow syndrome and dystocia at calving.'
                ),
                cattle=cattle,
                farm=farm,
                dedupe_key=f'bcs-high-dry-{cattle.id}-{date.isoformat()}',
            )

    return log

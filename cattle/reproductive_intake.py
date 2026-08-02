"""Onboard reproductive history when creating female cattle."""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError


@transaction.atomic
def apply_reproductive_intake(
    cattle,
    *,
    is_pregnant=None,
    insemination_date=None,
    insemination_sire=None,
    insemination_sire_external_id=None,
    breeding_method='AI',
    previous_calvings=None,
    last_calving_date=None,
):
    """
    Seed pregnancy / prior calving history for a newly registered female.

    - Calves / young heifers below first-breeding age skip intake.
    - If non-pregnant and last_calving_date is provided for a mature female,
      creates a single authentic BirthRecord.
    - If is_pregnant, creates a confirmed Pregnancy linked to an AI/mating event.
    """
    from breeding.models import BirthRecord, BreedingEvent, Pregnancy
    from husbandry.services import get_settings

    if cattle.sex != cattle.Sex.FEMALE:
        if any(
            v not in (None, False, 0, '')
            for v in (is_pregnant, insemination_date, previous_calvings, last_calving_date)
        ):
            raise ValidationError(
                {'sex': 'Pregnancy and calving history apply to female cattle only.'}
            )
        return

    settings = get_settings(cattle.farm)
    today = timezone.localdate()
    age_days = cattle.age_days
    breeding_ready = age_days is None or age_days >= settings.first_breeding_age_days

    # Young animals: ignore empty intake; reject meaningful reproductive claims
    if not breeding_ready and not is_pregnant and not last_calving_date:
        return

    if not breeding_ready and (is_pregnant or last_calving_date):
        raise ValidationError(
            {
                'date_of_birth': (
                    f'This animal is under typical first-breeding age '
                    f'({settings.first_breeding_age_days} days). '
                    'Leave pregnancy and calving history empty for calves / young heifers.'
                )
            }
        )

    if is_pregnant and not insemination_date:
        raise ValidationError(
            {'insemination_date': 'Insemination / mating date is required when pregnant.'}
        )

    if last_calving_date and last_calving_date > today:
        raise ValidationError({'last_calving_date': 'Last calving date cannot be in the future.'})

    if insemination_date and insemination_date > today:
        raise ValidationError({'insemination_date': 'Insemination date cannot be in the future.'})

    if (
        last_calving_date
        and cattle.date_of_birth
        and last_calving_date < cattle.date_of_birth
    ):
        raise ValidationError({'last_calving_date': 'Last calving date cannot be before date of birth.'})

    if (
        last_calving_date
        and cattle.date_of_birth
        and (last_calving_date - cattle.date_of_birth).days < settings.weaning_days
    ):
        raise ValidationError({'last_calving_date': 'Last calving date cannot be when the animal was a calf.'})

    # --- Current pregnancy ---
    if is_pregnant:
        method = breeding_method if breeding_method in ('AI', 'NATURAL') else 'AI'
        event = BreedingEvent.objects.create(
            farm=cattle.farm,
            dam=cattle,
            mating_date=insemination_date,
            sire=insemination_sire,
            sire_external_id=insemination_sire_external_id or '',
            method=method,
            notes='Recorded during animal onboarding.',
        )
        # Signal creates OPEN pregnancy — promote to confirmed PREGNANT
        pregnancy = (
            Pregnancy.objects.filter(cattle=cattle, breeding_event=event)
            .order_by('-created_at')
            .first()
        )
        if pregnancy is None:
            pregnancy = Pregnancy.objects.create(
                farm=cattle.farm,
                cattle=cattle,
                breeding_event=event,
                expected_calving_date=insemination_date
                + timedelta(days=settings.gestation_days),
                status=Pregnancy.Status.PREGNANT,
                confirmed_on=today,
                clinical_notes='Confirmed pregnant at onboarding.',
            )
        else:
            pregnancy.status = Pregnancy.Status.PREGNANT
            pregnancy.confirmed_on = today
            pregnancy.expected_calving_date = insemination_date + timedelta(
                days=settings.gestation_days
            )
            pregnancy.clinical_notes = (
                (pregnancy.clinical_notes or '') + ' Confirmed pregnant at onboarding.'
            ).strip()
            pregnancy.save(
                update_fields=[
                    'status',
                    'confirmed_on',
                    'expected_calving_date',
                    'clinical_notes',
                    'updated_at',
                ]
            )

    # --- Single explicit last calving record (for non-pregnant mature cow) ---
    elif last_calving_date:
        mating_est = last_calving_date - timedelta(days=settings.gestation_days)
        preg = Pregnancy.objects.create(
            farm=cattle.farm,
            cattle=cattle,
            confirmed_on=mating_est + timedelta(days=settings.pregnancy_check_days),
            expected_calving_date=last_calving_date,
            status=Pregnancy.Status.CALVED,
            clinical_notes='Historical pregnancy from animal onboarding.',
        )
        BirthRecord.objects.create(
            farm=cattle.farm,
            pregnancy=preg,
            calving_date=last_calving_date,
            notes='Last calving record registered during animal onboarding.',
        )

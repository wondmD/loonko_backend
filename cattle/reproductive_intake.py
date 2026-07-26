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
    breeding_method='AI',
    previous_calvings=0,
    last_calving_date=None,
):
    """
    Seed pregnancy / prior calving history for a newly registered female.

    - Calves / young heifers below first-breeding age skip intake.
    - previous_calvings creates historical BirthRecords (no calf animals).
    - is_pregnant creates a confirmed Pregnancy linked to an AI/mating event.
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

    previous_calvings = int(previous_calvings or 0)
    if previous_calvings < 0 or previous_calvings > 20:
        raise ValidationError({'previous_calvings': 'Enter a number between 0 and 20.'})

    # Young animals: ignore empty intake; reject meaningful reproductive claims
    if not breeding_ready and previous_calvings == 0 and not is_pregnant:
        return

    if not breeding_ready and (is_pregnant or previous_calvings > 0):
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

    if previous_calvings > 0 and last_calving_date is None:
        # Estimate most recent calving ~1 year before today (or before mating if pregnant)
        anchor = insemination_date or today
        last_calving_date = anchor - timedelta(days=365)

    if last_calving_date and last_calving_date > today:
        raise ValidationError({'last_calving_date': 'Last calving date cannot be in the future.'})

    if insemination_date and insemination_date > today:
        raise ValidationError({'insemination_date': 'Insemination date cannot be in the future.'})

    if (
        last_calving_date
        and cattle.date_of_birth
        and last_calving_date < cattle.date_of_birth + timedelta(days=settings.first_breeding_age_days)
    ):
        # Soft guard — still allow if farmer insists via slightly early estimate
        pass

    # --- Historical calvings (oldest → newest) ---
    if previous_calvings > 0:
        dates = []
        cursor = last_calving_date
        for _ in range(previous_calvings):
            dates.append(cursor)
            cursor = cursor - timedelta(days=365)
        dates.reverse()

        for index, calving_date in enumerate(dates, start=1):
            if cattle.date_of_birth and calving_date < cattle.date_of_birth:
                calving_date = cattle.date_of_birth + timedelta(days=settings.first_breeding_age_days)
            mating_est = calving_date - timedelta(days=settings.gestation_days)
            preg = Pregnancy.objects.create(
                farm=cattle.farm,
                cattle=cattle,
                confirmed_on=mating_est + timedelta(days=settings.pregnancy_check_days),
                expected_calving_date=calving_date,
                status=Pregnancy.Status.CALVED,
                clinical_notes='Historical pregnancy from animal onboarding.',
            )
            BirthRecord.objects.create(
                farm=cattle.farm,
                pregnancy=preg,
                calving_date=calving_date,
                notes=f'Historical calving #{index} of {previous_calvings} (onboarding).',
            )

    # --- Current pregnancy ---
    if is_pregnant:
        method = breeding_method if breeding_method in ('AI', 'NATURAL') else 'AI'
        event = BreedingEvent.objects.create(
            farm=cattle.farm,
            dam=cattle,
            mating_date=insemination_date,
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

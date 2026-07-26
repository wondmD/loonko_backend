from datetime import timedelta

from django.db import models
from django.db.models import Sum, F
from django.utils import timezone


class Cattle(models.Model):
    class Sex(models.TextChoices):
        FEMALE = 'FEMALE', 'Female'
        MALE = 'MALE', 'Male'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        SOLD = 'SOLD', 'Sold'
        DEAD = 'DEAD', 'Dead'
        CULLED = 'CULLED', 'Culled'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='cattle',
    )
    tag_id = models.CharField(max_length=64)
    name = models.CharField(max_length=128, blank=True)
    breed = models.CharField(max_length=128, blank=True)
    sex = models.CharField(max_length=10, choices=Sex.choices, default=Sex.FEMALE)
    date_of_birth = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    mother = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='offspring_as_mother',
    )
    father = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='offspring_as_father',
    )
    notes = models.TextField(blank=True)
    photo_front = models.ImageField(
        upload_to='cattle/front/',
        blank=True,
        null=True,
        help_text='Front view for identification.',
    )
    photo_left = models.ImageField(
        upload_to='cattle/left/',
        blank=True,
        null=True,
        help_text='Left side view.',
    )
    photo_right = models.ImageField(
        upload_to='cattle/right/',
        blank=True,
        null=True,
        help_text='Right side view.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Dairy planning defaults (days)
    LACTATION_TARGET_DAYS = 305
    DRY_PERIOD_DAYS = 60
    VOLUNTARY_WAITING_DAYS = 60
    ESTROUS_CYCLE_DAYS = 21

    class Meta:
        ordering = ['tag_id']
        verbose_name_plural = 'cattle'
        constraints = [
            models.UniqueConstraint(fields=['farm', 'tag_id'], name='uniq_cattle_farm_tag'),
        ]
        indexes = [
            models.Index(fields=['farm', 'status']),
            models.Index(fields=['farm', 'tag_id']),
        ]

    def __str__(self):
        return f'{self.tag_id} ({self.name or self.breed or "cattle"})'

    @property
    def age_days(self):
        if not self.date_of_birth:
            return None
        return (timezone.localdate() - self.date_of_birth).days

    def last_calving_date(self):
        from breeding.models import BirthRecord

        birth = (
            BirthRecord.objects.filter(pregnancy__cattle=self)
            .order_by('-calving_date')
            .first()
        )
        return birth.calving_date if birth else None

    def active_pregnancy(self):
        return (
            self.pregnancies.filter(status='PREGNANT')
            .order_by('-expected_calving_date', '-created_at')
            .first()
        )

    def last_breeding_event(self):
        return self.breeding_as_dam.order_by('-mating_date').first()

    def lactation_info(self):
        """Compute lactation stage and related metrics for females."""
        today = timezone.localdate()
        if self.sex != self.Sex.FEMALE:
            return {
                'stage': 'N/A',
                'stage_label': 'Not applicable (male)',
                'days_in_milk': None,
                'last_calving_date': None,
                'is_pregnant': False,
            }

        pregnancy = self.active_pregnancy()
        last_calving = self.last_calving_date()
        dim = (today - last_calving).days if last_calving else None

        if pregnancy and pregnancy.expected_calving_date:
            days_to_calving = (pregnancy.expected_calving_date - today).days
            if days_to_calving <= self.DRY_PERIOD_DAYS:
                stage, label = 'DRY', 'Dry period (pre-calving)'
            else:
                if dim is None:
                    stage, label = 'PREGNANT', 'Pregnant'
                elif dim <= 21:
                    stage, label = 'FRESH', 'Fresh (early lactation)'
                elif dim <= 100:
                    stage, label = 'PEAK', 'Peak lactation'
                elif dim <= 200:
                    stage, label = 'MID', 'Mid lactation'
                else:
                    stage, label = 'LATE', 'Late lactation'
        elif last_calving is None:
            stage, label = 'HEIFER', 'Heifer / never calved'
            dim = None
        else:
            milking_end = self.LACTATION_TARGET_DAYS - self.DRY_PERIOD_DAYS
            if dim > milking_end:
                stage, label = 'DRY', 'Dry / extended lactation'
            elif dim <= 21:
                stage, label = 'FRESH', 'Fresh (early lactation)'
            elif dim <= 100:
                stage, label = 'PEAK', 'Peak lactation'
            elif dim <= 200:
                stage, label = 'MID', 'Mid lactation'
            else:
                stage, label = 'LATE', 'Late lactation'

        return {
            'stage': stage,
            'stage_label': label,
            'days_in_milk': dim,
            'last_calving_date': last_calving.isoformat() if last_calving else None,
            'is_pregnant': bool(pregnancy),
        }

    def upcoming_events(self):
        """Next real care milestones: husbandry tasks, pregnancy ECD, vaccinations."""
        today = timezone.localdate()
        events = []
        seen = set()

        def add(event_type, title, date_value, description=''):
            if not date_value:
                return
            key = (event_type, date_value.isoformat(), title)
            if key in seen:
                return
            seen.add(key)
            events.append(
                {
                    'type': event_type,
                    'title': title,
                    'date': date_value.isoformat(),
                    'days_until': (date_value - today).days,
                    'description': description,
                }
            )

        # 1) Scheduled husbandry tasks (authoritative upcoming work)
        from husbandry.models import HusbandryTask

        tasks = (
            self.husbandry_tasks.filter(status=HusbandryTask.Status.PENDING)
            .order_by('due_date', 'priority')[:8]
        )
        for task in tasks:
            add(
                task.task_type,
                task.title,
                task.due_date,
                task.description or task.get_task_type_display(),
            )

        # 2) Confirmed pregnancy milestones if not already covered by tasks
        if self.sex == self.Sex.FEMALE:
            pregnancy = self.active_pregnancy()
            if pregnancy and pregnancy.expected_calving_date:
                ecd = pregnancy.expected_calving_date
                dry_off = ecd - timedelta(days=self.DRY_PERIOD_DAYS)
                if dry_off >= today - timedelta(days=7):
                    add(
                        'DRY_OFF',
                        'Dry-off',
                        dry_off,
                        'Target dry-off before expected calving.',
                    )
                add(
                    'CALVING',
                    'Expected calving',
                    ecd,
                    'From confirmed pregnancy record.',
                )

            # 3) Planning windows when no pending task covers the next step
            if not any(e['days_until'] >= 0 for e in events):
                from husbandry.planning import suggested_windows

                plan = suggested_windows(self)
                for window in plan.get('windows') or []:
                    if window.get('status') not in ('UPCOMING', 'ACTIVE', 'OVERDUE'):
                        continue
                    ideal = window.get('ideal') or window.get('start')
                    if not ideal:
                        continue
                    try:
                        from datetime import date as date_cls

                        if isinstance(ideal, str):
                            ideal_date = date_cls.fromisoformat(ideal)
                        else:
                            ideal_date = ideal
                    except (TypeError, ValueError):
                        continue
                    add(
                        window.get('key') or 'CARE',
                        window.get('title') or 'Upcoming care',
                        ideal_date,
                        window.get('description') or window.get('message') or '',
                    )
                    break

        # 4) Upcoming vaccinations
        from health.models import Vaccination

        for vac in Vaccination.objects.filter(
            cattle=self,
            next_due_on__isnull=False,
            next_due_on__gte=today - timedelta(days=3),
        ).order_by('next_due_on')[:5]:
            add(
                'VACCINATION',
                f'Vaccination: {vac.vaccine_name}',
                vac.next_due_on,
                'Scheduled vaccination.',
            )

        events.sort(key=lambda e: e['date'])
        return events

    def milk_summary(self):
        from milk.models import MilkRecord

        today = timezone.localdate()
        qs = MilkRecord.objects.filter(cattle=self).annotate(
            total=F('morning_liters') + F('evening_liters')
        )
        last_30 = qs.filter(date__gte=today - timedelta(days=30))
        lifetime = qs.aggregate(lifetime=Sum('total'))['lifetime'] or 0
        record_count_30 = last_30.count()
        liters_30 = last_30.aggregate(liters=Sum('total'))['liters'] or 0
        latest = qs.order_by('-date').first()
        return {
            'lifetime_liters': lifetime,
            'last_30_days_liters': liters_30,
            'last_30_days_records': record_count_30,
            'latest_date': latest.date.isoformat() if latest else None,
            'latest_liters': float(latest.total) if latest else None,
            'average_daily_30': (
                float(liters_30) / record_count_30 if record_count_30 else 0
            ),
        }

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Avg, F
from django.utils import timezone


class MilkRecord(models.Model):
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='milk_records',
    )
    cattle = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='milk_records')
    date = models.DateField()
    morning_liters = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    evening_liters = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='milk_records',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'cattle_id']
        unique_together = [('cattle', 'date')]
        indexes = [
            models.Index(fields=['farm', 'date']),
            models.Index(fields=['cattle', 'date']),
        ]

    def __str__(self):
        return f'{self.cattle.tag_id} @ {self.date}: {self.total_liters}L'

    @property
    def total_liters(self):
        return (self.morning_liters or 0) + (self.evening_liters or 0)


class FeedSchedule(models.Model):
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='feed_schedules',
    )
    cattle = models.ForeignKey(
        'cattle.Cattle',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='feed_schedules',
    )
    feed_type = models.CharField(max_length=128)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=32, default='kg')
    date = models.DateField(default=timezone.localdate)
    quality_score = models.PositiveSmallIntegerField(null=True, blank=True)
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Optional cost booked as a feed expense.',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['farm', 'date'])]

    def __str__(self):
        target = self.cattle.tag_id if self.cattle_id else 'herd'
        return f'{self.feed_type} for {target} on {self.date}'


def cow_recent_average(cattle, before_date, days=14):
    qs = MilkRecord.objects.filter(
        cattle=cattle,
        date__lt=before_date,
        date__gte=before_date - timedelta(days=days),
    )
    totals = qs.annotate(total=F('morning_liters') + F('evening_liters')).aggregate(
        avg=Avg('total')
    )
    return totals['avg']

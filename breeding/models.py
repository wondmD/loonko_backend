from django.db import models, transaction


class BreedingEvent(models.Model):
    class Method(models.TextChoices):
        NATURAL = 'NATURAL', 'Natural'
        AI = 'AI', 'Artificial Insemination'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='breeding_events',
    )
    dam = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='breeding_as_dam')
    sire = models.ForeignKey(
        'cattle.Cattle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='breeding_as_sire',
    )
    sire_external_id = models.CharField(max_length=128, blank=True)
    mating_date = models.DateField()
    method = models.CharField(max_length=16, choices=Method.choices, default=Method.NATURAL)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-mating_date']
        indexes = [models.Index(fields=['farm', 'mating_date'])]

    def __str__(self):
        return f'Breeding {self.dam.tag_id} @ {self.mating_date}'


class Pregnancy(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        PREGNANT = 'PREGNANT', 'Pregnant'
        CALVED = 'CALVED', 'Calved'
        FAILED = 'FAILED', 'Failed'

    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='pregnancies',
    )
    cattle = models.ForeignKey('cattle.Cattle', on_delete=models.CASCADE, related_name='pregnancies')
    breeding_event = models.ForeignKey(
        BreedingEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pregnancies',
    )
    confirmed_on = models.DateField(null=True, blank=True)
    expected_calving_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PREGNANT)
    clinical_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expected_calving_date', '-created_at']
        verbose_name_plural = 'pregnancies'
        indexes = [models.Index(fields=['farm', 'status'])]

    def __str__(self):
        return f'Pregnancy {self.cattle.tag_id} ({self.status})'


class BirthRecord(models.Model):
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        related_name='birth_records',
    )
    pregnancy = models.OneToOneField(Pregnancy, on_delete=models.CASCADE, related_name='birth')
    calving_date = models.DateField()
    calf = models.ForeignKey(
        'cattle.Cattle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='birth_record',
    )
    calf_tag_id = models.CharField(max_length=64, blank=True)
    calf_sex = models.CharField(max_length=10, blank=True)
    complications = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-calving_date']
        indexes = [models.Index(fields=['farm', 'calving_date'])]

    def __str__(self):
        return f'Birth from pregnancy {self.pregnancy_id} @ {self.calving_date}'

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.farm_id is None and self.pregnancy_id:
            self.farm_id = self.pregnancy.farm_id
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.calf_id and self.calf_tag_id:
            from cattle.models import Cattle

            sire = None
            sire_external = ''
            if self.pregnancy.breeding_event_id:
                ev = self.pregnancy.breeding_event
                sire = ev.sire
                sire_external = ev.sire_external_id

            calf = Cattle.objects.create(
                farm_id=self.farm_id,
                tag_id=self.calf_tag_id,
                sex=self.calf_sex or Cattle.Sex.FEMALE,
                date_of_birth=self.calving_date,
                mother=self.pregnancy.cattle,
                father=sire,
                father_external_id=sire_external,
                status=Cattle.Status.ACTIVE,
            )
            BirthRecord.objects.filter(pk=self.pk).update(calf=calf)
            self.calf = calf
        if self.pregnancy.status != Pregnancy.Status.CALVED:
            self.pregnancy.status = Pregnancy.Status.CALVED
            self.pregnancy.save(update_fields=['status', 'updated_at'])

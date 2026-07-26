from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Farm Owner'
        WORKER = 'WORKER', 'Worker'
        VETERINARIAN = 'VETERINARIAN', 'Veterinarian'

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=32, blank=True, null=True, unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.OWNER)
    farm = models.ForeignKey(
        'farm.Farm',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users',
        help_text='Tenant farm. Null only for platform superusers.',
    )
    is_active_staff_member = models.BooleanField(
        default=True,
        help_text='Deactivate invited staff without deleting the account.',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return f'{self.email} ({self.role})'

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_worker(self):
        return self.role == self.Role.WORKER

    @property
    def is_veterinarian(self):
        return self.role == self.Role.VETERINARIAN

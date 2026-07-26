from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('email', 'username', 'role', 'is_active', 'is_staff', 'is_superuser')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'phone')
    ordering = ('email',)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Farm role', {'fields': ('role', 'phone', 'is_active_staff_member')}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('Farm role', {'fields': ('role', 'email', 'phone')}),
    )

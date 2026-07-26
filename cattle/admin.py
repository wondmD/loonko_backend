from django.contrib import admin
from django.utils.html import format_html

from .models import Cattle


@admin.register(Cattle)
class CattleAdmin(admin.ModelAdmin):
    list_display = (
        'tag_id',
        'name',
        'breed',
        'sex',
        'status',
        'date_of_birth',
        'has_photos',
    )
    list_filter = ('status', 'sex', 'breed')
    search_fields = ('tag_id', 'name')
    readonly_fields = ('photo_preview',)

    def has_photos(self, obj):
        return bool(obj.photo_front and obj.photo_left and obj.photo_right)

    has_photos.boolean = True
    has_photos.short_description = '3 photos'

    def photo_preview(self, obj):
        parts = []
        for label, field in (
            ('Front', obj.photo_front),
            ('Left', obj.photo_left),
            ('Right', obj.photo_right),
        ):
            if field:
                parts.append(
                    f'<div style="display:inline-block;margin:4px;text-align:center">'
                    f'<img src="{field.url}" style="max-height:100px;border-radius:8px;" />'
                    f'<div>{label}</div></div>'
                )
        return format_html(''.join(parts)) if parts else '—'

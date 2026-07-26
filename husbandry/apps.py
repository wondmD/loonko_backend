from django.apps import AppConfig


class HusbandryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'husbandry'
    verbose_name = 'Cattle Husbandry'

    def ready(self):
        from . import signals  # noqa: F401

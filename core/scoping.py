"""Mixins for farm-scoped DRF viewsets."""

from core.farm_utils import require_user_farm


class FarmScopedQuerySetMixin:
    """
    Filter querysets to request.user.farm and stamp farm on create.
    Viewsets may set farm_field = 'farm' (default).
    """

    farm_field = 'farm'

    def get_user_farm(self):
        return require_user_farm(self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        farm = self.get_user_farm()
        return qs.filter(**{self.farm_field: farm})

    def perform_create(self, serializer):
        farm = self.get_user_farm()
        serializer.save(**{self.farm_field: farm})

from rest_framework.exceptions import PermissionDenied, ValidationError


def get_user_farm(user):
    """Return the authenticated user's farm, or None."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return getattr(user, 'farm', None)


def require_user_farm(user):
    farm = get_user_farm(user)
    if farm is None:
        raise PermissionDenied('Your account is not linked to a farm.')
    return farm


def create_farm_for_owner(*, name, owner=None, **extra):
    """Create a new farm (and optionally attach the owner)."""
    from farm.models import Farm

    farm = Farm.objects.create(name=name or 'My Dairy Farm', **extra)
    if owner is not None:
        owner.farm = farm
        owner.save(update_fields=['farm'])
    return farm

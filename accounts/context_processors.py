
from .models import UserPreference


def user_appearance(request):
    if request.user.is_authenticated:
        preference, created = UserPreference.objects.get_or_create(
            user=request.user,
            defaults={"theme": "system"},
        )
        return {
            "user_preference": preference,
            "preference": preference,
        }

    return {
        "user_preference": None,
        "preference": None,
    }

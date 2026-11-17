
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from core.permissions import staff_required, superuser_required
from billing.models import ShopSetting
from billing.forms import ShopSettingForm


@login_required
def home(request):
    """Main landing page with the two primary areas of the POS."""
    return render(request, "pos/home.html")


@staff_required
def management_home(request):
    """Central hub for staff-only management workflows."""
    return render(request, "pos/management.html")


@superuser_required
def settings_view(request):
    """Administrator-only POS business settings."""
    settings = ShopSetting.objects.first()

    if settings is None:
        settings = ShopSetting()

    if request.method == "POST":
        form = ShopSettingForm(
            request.POST,
            request.FILES,
            instance=settings,
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Business settings updated successfully."
            )
            return redirect("pos_settings")
    else:
        form = ShopSettingForm(instance=settings)

    return render(
        request,
        "pos/settings.html",
        {
            "form": form,
            "settings": settings,
            "page": "pos_settings",
        },
    )

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.permissions import staff_required


@login_required
def home(request):
    """Main landing page with the two primary areas of the POS."""
    return render(request, "pos/home.html")


@staff_required
def management_home(request):
    """Central hub for staff-only management workflows."""
    return render(request, "pos/management.html")

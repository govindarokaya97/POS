
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("home/", include("pos.urls")),
    path("", include("accounts.urls")),
    path("inventory/", include("inventory.urls")),
    path("sales/", include("sales.urls")),
    path("billing/", include("billing.urls")),
    path("cinema/", include("cinema.urls")),
]


from django.urls import path
from . import views


urlpatterns = [
    path("", views.home, name="pos_home"),
    path("management/", views.management_home, name="management_home"),
    path("settings/", views.settings_view, name="pos_settings"),
]

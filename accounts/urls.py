from django.urls import path
from . import views

urlpatterns = [
    path('user/register', views.register, name="register"),
    path('', views.login_user, name="login"),
    path('user/logout', views.logout_user, name="logout"),
    path('dashboard/', views.dashboard, name="dashboard"),
]
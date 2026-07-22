from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_dashboard, name='sales_dashboard'),
    path("create/", views.create_sales, name="create_sales"),
    path('history/', views.sales_history, name='sales_history'),
    

]

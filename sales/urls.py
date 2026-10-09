from django.urls import path
from . import views

urlpatterns = [
    path('', views.sales_dashboard, name='sales_dashboard'),
    path("create/", views.create_sales, name="create_sales"),
    path('history/', views.sales_history, name='sales_history'),
    path(
        "export/csv/",
        views.export_sales_csv,
        name="export_sales_csv"
    ),


    path(
        "export/pdf/",
        views.export_sales_pdf,
        name="export_sales_pdf"
    ),

]

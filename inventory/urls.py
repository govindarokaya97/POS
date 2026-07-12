from django.urls import path
from . import views

urlpatterns =[
    path("category/",views.categories, name="category"),
    path("category/add/", views.add_categories, name="add_category"),
    path("category/update/", views.update_categories, name="update_category"),
    path("category/view/", views.view_categories, name="view_category"),

    path("category/update/<int:id>", views.update_categories, name="update_category"),


    path("product/", views.products, name="products"),
    path("product/add", views.add_products, name="add_products"),
    path("product/view", views.view_product, name="view_products"),



]
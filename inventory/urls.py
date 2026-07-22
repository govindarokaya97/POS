from django.urls import path
from . import views

urlpatterns =[
    path("category/",views.categories, name="category"),
    path("category/add/", views.add_categories, name="add_category"),
    path("category/update/", views.update_categories, name="update_category"),
    path("category/view/", views.view_categories, name="view_category"),

    path("category/update/<int:id>", views.update_categories, name="update_category"),
    path("category/delete/<int:id>", views.delete_category , name="delete_category"),


    path("product/", views.products, name="products"),
    path("product/add", views.add_product, name="add_product"),
    path("product/view", views.view_product, name="view_product"),
    path("product/update/<int:id>", views.update_product , name="update_product"),
    path("product/delete/<int:id>", views.delete_product , name="delete_product"),


]
from django.urls import path
from . import views

urlpatterns = [

    # Categories
    path("category/", views.category_list, name="category"),
    path("category/add/", views.add_categories, name="add_category"),
    path("category/<int:id>/edit/", views.update_categories, name="update_category"),
    path("category/<int:id>/delete/", views.delete_category, name="delete_category"),

    # Products
    path("product/", views.product_list, name="view_product"),
    path("product/add/", views.add_product, name="add_product"),
    path("product/<int:id>/", views.product_detail, name="product_detail"),
    path("product/<int:id>/edit/", views.update_product, name="update_product"),
    path("product/<int:id>/delete/", views.delete_product, name="delete_product"),
]
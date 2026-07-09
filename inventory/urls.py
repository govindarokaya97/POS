from django.urls import path
from . import views

urlpatterns =[
    path("category/",views.categories, name="category"),
    path("category/add/", views.add_categories, name="add_category"),
    path("category/update/", views.update_categories, name="update_category"),
    path("category/view/", views.view_categories, name="view_category"),

    path("category/update/<int:id>", views.update_categories, name="update_category"),

]
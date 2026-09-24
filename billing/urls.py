from django.urls import path
from . import views


urlpatterns = [

    path(
        "",
        views.cart_view,
        name="cart"
    ),


    path(
        "add/<int:product_id>/",
        views.add_to_cart,
        name="add_to_cart"
    ),


    path(
        "remove/<int:product_id>/",
        views.remove_from_cart,
        name="remove_from_cart"
    ),


    path(
        "increase/<int:product_id>/",
        views.increase_quantity,
        name="increase_quantity"
    ),


    path(
        "decrease/<int:product_id>/",
        views.decrease_quantity,
        name="decrease_quantity"
    ),

    path(
        "clear/",
        views.clear_cart,
        name="clear_cart"
    ),

    path(
        "checkout/",
        views.checkout,
        name="checkout"
    ),

    path(
        "invoice/<int:id>/",
        views.invoice_detail,
        name="invoice"
    ),


    path(
        "products/",
        views.billing_products,
        name="billing_products"
    ),


    path(
        "customers/",
        views.customers,
        name="customers"
    ),


    path(
        "customers/add/",
        views.add_customer,
        name="add_customer"
    ),

]
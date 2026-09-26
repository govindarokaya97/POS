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

    path(
        "customers/<int:id>/",
        views.customer_detail,
        name="customer_detail"
    ),

    path(
        "expenses/",
        views.expenses,
        name="expenses"
    ),


    path(
        "expenses/add/",
        views.add_expense,
        name="add_expense"
    ),

    path(
        "reports/",
        views.sales_report,
        name="sales_report"
    ),


    path(
        "reports/export/csv/",
        views.export_sales_csv,
        name="export_sales_csv"
    ),

    path(
        "reports/export/pdf/",
        views.export_sales_pdf,
        name="export_sales_pdf"
    ),

    path(
        "scan/<str:barcode>/",
        views.scan_barcode,
        name="scan_barcode"
    ),

]
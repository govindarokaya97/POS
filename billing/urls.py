from django.urls import path
from . import views


urlpatterns = [

    # Billing dashboard

    path(
        "",
        views.billing_products,
        name="billing_products"
    ),


    path(
        "dashboard/",
        views.sales_dashboard,
        name="dashboard"
    ),



    # Cart

    path(
        "cart/",
        views.cart_view,
        name="cart"
    ),


    path(
        "add/<int:product_id>/",
        views.add_to_cart,
        name="add_to_cart"
    ),



    path(
        "cart/increase/<int:product_id>/",
        views.increase_quantity,
        name="increase_cart",
    ),

    path(
        "cart/decrease/<int:product_id>/",
        views.decrease_quantity,
        name="decrease_cart",
    ),


    path(
        "cart/remove/<int:product_id>/",
        views.remove_cart,
        name="remove_cart"
    ),



    path(
        "cart/clear/",
        views.clear_cart,
        name="clear_cart"
    ),




    # Checkout

    path(
        "checkout/",
        views.checkout,
        name="checkout"
    ),





    # Invoice

    path(
        "invoice/<int:id>/",
        views.invoice_detail,
        name="invoice"
    ),


    path(
        "invoice/<int:id>/pdf/",
        views.invoice_pdf,
        name="invoice_pdf"
    ),




    # Barcode Scanner

    path(
        "scan-barcode/",
        views.scan_barcode,
        name="scan_barcode"
    ),





    # Customers

    path(
        "customers/",
        views.customer_list,
        name="customer_list"
    ),


    path(
        "customers/add/",
        views.customer_create,
        name="customer_create"
    ),


    path(
        "customers/<int:id>/",
        views.customer_detail,
        name="customer_detail"
    ),


    path(
        "customers/<int:id>/edit/",
        views.customer_edit,
        name="customer_edit"
    ),


    path(
        "customers/<int:id>/delete/",
        views.customer_delete,
        name="customer_delete"
    ),


    path(
        "customers/<int:id>/statement/",
        views.customer_statement_pdf,
        name="customer_statement_pdf"
    ),





    # Expenses

    path(
        "expense-categories/",
        views.expense_category_list,
        name="expense_category_list"
    ),


    path(
        "expense-categories/create/",
        views.expense_category_create,
        name="expense_category_create"
    ),


    path(
        "expense-categories/<int:id>/edit/",
        views.expense_category_edit,
        name="expense_category_edit"
    ),


    path(
        "expense-categories/<int:id>/delete/",
        views.expense_category_delete,
        name="expense_category_delete"
    ),



    path(
        "expenses/",
        views.expense_list,
        name="expense_list"
    ),


    path(
        "expenses/add/",
        views.expense_create,
        name="expense_create"
    ),


    path(
        "expenses/<int:id>/edit/",
        views.expense_edit,
        name="expense_edit"
    ),


    path(
        "expenses/<int:id>/",
        views.expense_detail,
        name="expense_detail"
    ),


    path(
        "expenses/<int:id>/delete/",
        views.expense_delete,
        name="expense_delete"
    ),



    path(
        "expenses/export/csv/",
        views.expense_export_csv,
        name="expense_export_csv"
    ),


    path(
        "expenses/export/pdf/",
        views.expense_export_pdf,
        name="expense_export_pdf"
    ),





    # Reports

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

]
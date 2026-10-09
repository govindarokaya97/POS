import logging
from django.shortcuts import redirect, render


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction

from billing.models import Invoice
from django.db.models import Q, Sum
from datetime import datetime

from inventory.models import Product
from .models import Sale

logger = logging.getLogger(__name__)


import csv

from django.http import HttpResponse

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Create your views here.
@login_required
def create_sales(request):
    products = Product.objects.filter(is_available=True)

    if request.method == "POST":
        product_id = request.POST.get("product")
        quantity_raw = request.POST.get("quantity")

        # 1. Validate input shape before touching the database at all.
        if not product_id:
            messages.error(request, "Please select a product.")
            return redirect("create_sales")

        try:
            quantity = int(quantity_raw)
            if quantity <= 0:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, "Quantity must be a whole number greater than zero.")
            return redirect("create_sales")

        try:
            # 2. select_for_update() locks the product row for the
            #    duration of the transaction, so two checkouts racing on
            #    the same product can't both pass the stock check and
            #    oversell it. Everything that reads/writes stock or
            #    creates the Sale happens inside this one atomic block,
            #    so a failure partway through leaves no partial state.
            with transaction.atomic():
                try:
                    product = Product.objects.select_for_update().get(
                        id=product_id, is_available=True
                    )
                except Product.DoesNotExist:
                    messages.error(request, "That product is no longer available.")
                    return redirect("create_sales")

                if quantity > product.stock:
                    messages.error(
                        request,
                        f"Not enough stock for {product.name} (only {product.stock} left).",
                    )
                    return redirect("create_sales")

                total_price = product.price * quantity
                Sale.objects.create(
                    product=product,
                    quantity=quantity,
                    total_price=total_price,
                    sold_by=request.user,
                )

                product.stock -= quantity
                if product.stock == 0:
                    product.is_available = False
                product.save()

        except Exception:
            # 3. Anything unexpected (DB connection drop, constraint
            #    violation, etc.) is a bug worth alerting on -- log the
            #    full traceback, but never show it to the cashier.
            logger.exception(
                "Unexpected error completing sale (product_id=%s, user=%s)",
                product_id, request.user.id,
            )
            messages.error(request, "Something went wrong completing the sale. Please try again.")
            return redirect("create_sales")

        messages.success(request, "Sale Completed")
        return redirect("dashboard")

    return render(request, "sales/create_sales.html", {"products": products})


@login_required
def sales_dashboard(request):
    today_revenue = Sale.objects.aggregate(revenue=Sum("total_price"))["revenue"] or 0
    today_sales_count = Sale.objects.count()
    products_sold = Sale.objects.aggregate(qty=Sum('quantity'))['qty'] or 0
    
    context = {
        'today_revenue' : today_revenue,
        'today_sales_count' : today_sales_count,
        'products_sold' : products_sold,
    }
    
    return render(request, "sales/sales.html", context)


@login_required
def sales_history(request):

    invoices = Invoice.objects.select_related(
        "customer"
    ).order_by("-created_at")


    # Filters

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    status = request.GET.get("status")


    if start_date:
        invoices = invoices.filter(
            created_at__date__gte=start_date
        )


    if end_date:
        invoices = invoices.filter(
            created_at__date__lte=end_date
        )


    if status:
        invoices = invoices.filter(
            payment_status=status
        )



    # Summary

    total_sales = invoices.count()


    total_amount = invoices.aggregate(
        total=Sum("total")
    )["total"] or 0


    paid_amount = invoices.aggregate(
        total=Sum("paid_amount")
    )["total"] or 0


    due_amount = invoices.aggregate(
        total=Sum("due_amount")
    )["total"] or 0



    context = {

        "invoices": invoices,

        "total_sales": total_sales,

        "total_amount": total_amount,

        "paid_amount": paid_amount,

        "due_amount": due_amount,

    }


    return render(
        request,
        "sales/history.html",
        context
    )


def get_filtered_invoices(request):

    invoices = Invoice.objects.select_related(
        "customer"
    ).order_by("-created_at")


    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    status = request.GET.get("status")


    if start_date:
        invoices = invoices.filter(
            created_at__date__gte=start_date
        )


    if end_date:
        invoices = invoices.filter(
            created_at__date__lte=end_date
        )


    if status:
        invoices = invoices.filter(
            payment_status=status
        )


    return invoices



@login_required
def export_sales_csv(request):

    invoices = get_filtered_invoices(request)


    response = HttpResponse(
        content_type="text/csv"
    )


    response["Content-Disposition"] = (
        'attachment; filename="sales_report.csv"'
    )


    writer = csv.writer(response)


    writer.writerow(
        [
            "Invoice",
            "Customer",
            "Total",
            "Paid",
            "Due",
            "Status",
            "Date"
        ]
    )


    for invoice in invoices:

        writer.writerow(
            [
                invoice.invoice_number,

                invoice.customer.name 
                if invoice.customer else "Walk-in",

                invoice.total,

                invoice.paid_amount,

                invoice.due_amount,

                invoice.payment_status,

                invoice.created_at.strftime(
                    "%Y-%m-%d"
                )
            ]
        )


    return response



from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors



@login_required
def export_sales_pdf(request):

    invoices = get_filtered_invoices(request)


    response = HttpResponse(
        content_type="application/pdf"
    )


    response["Content-Disposition"] = (
        'attachment; filename="sales_report.pdf"'
    )


    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )


    elements = []

    styles = getSampleStyleSheet()



    # TITLE

    title = Paragraph(
        "MY SHOP<br/>Sales Report",
        styles["Title"]
    )

    elements.append(title)


    elements.append(
        Spacer(1,20)
    )



    # Summary

    total_sales = sum(
        invoice.total 
        for invoice in invoices
    )


    total_paid = sum(
        invoice.paid_amount
        for invoice in invoices
    )


    total_due = sum(
        invoice.due_amount
        for invoice in invoices
    )


    summary_data = [

        ["Total Invoice", len(invoices)],

        ["Total Sales", f"Rs {total_sales}"],

        ["Paid Amount", f"Rs {total_paid}"],

        ["Due Amount", f"Rs {total_due}"],

    ]



    summary_table = Table(
        summary_data,
        colWidths=[150,150]
    )


    summary_table.setStyle(
        TableStyle([

            (
                "GRID",
                (0,0),
                (-1,-1),
                0.5,
                colors.grey
            ),

            (
                "BACKGROUND",
                (0,0),
                (-1,0),
                colors.lightgrey
            ),

            (
                "PADDING",
                (0,0),
                (-1,-1),
                8
            ),

        ])
    )


    elements.append(summary_table)


    elements.append(
        Spacer(1,30)
    )




    # Invoice table


    data = [

        [
            "Invoice",
            "Customer",
            "Amount",
            "Paid",
            "Due",
            "Status",
            "Date"
        ]

    ]



    for invoice in invoices:

        data.append(

            [

                invoice.invoice_number,

                invoice.customer.name
                if invoice.customer
                else "Walk-in",

                f"Rs {invoice.total}",

                f"Rs {invoice.paid_amount}",

                f"Rs {invoice.due_amount}",

                invoice.payment_status.title(),

                invoice.created_at.strftime(
                    "%Y-%m-%d"
                ),

            ]

        )



    table = Table(
        data,
        repeatRows=1
    )



    table.setStyle(

        TableStyle([


            (
                "GRID",
                (0,0),
                (-1,-1),
                0.5,
                colors.grey
            ),


            (
                "BACKGROUND",
                (0,0),
                (-1,0),
                colors.darkgrey
            ),


            (
                "TEXTCOLOR",
                (0,0),
                (-1,0),
                colors.white
            ),


            (
                "ALIGN",
                (2,1),
                (-2,-1),
                "RIGHT"
            ),


            (
                "PADDING",
                (0,0),
                (-1,-1),
                6
            ),

        ])

    )


    elements.append(table)



    elements.append(
        Spacer(1,30)
    )


    footer = Paragraph(
        "Thank you for your business.",
        styles["Normal"]
    )


    elements.append(
        footer
    )


    doc.build(elements)


    return response



    
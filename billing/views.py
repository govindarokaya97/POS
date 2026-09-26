from django.shortcuts import render
from django.shortcuts import render,redirect,get_object_or_404
from inventory.models import Product

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Invoice, InvoiceItem, Customer

import csv
from reportlab.pdfgen import canvas
from django.http import HttpResponse

from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta

from inventory.models import Product
from decimal import Decimal
from django.db import transaction

@login_required
def sales_dashboard(request):

    today = timezone.now().date()


    today_invoices = Invoice.objects.filter(
        created_at__date=today
    )


    today_sales = today_invoices.aggregate(
        total=Sum("total")
    )["total"] or 0


    today_expenses = Expense.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Sum("amount")
    )["total"] or 0



    today_profit = (
        today_sales -
        today_expenses
    )

    total_invoices = Invoice.objects.count()



    pending_payment = Invoice.objects.filter(
        due_amount__gt=0
    ).aggregate(
        total=Sum("due_amount")
    )["total"] or 0



    products_sold = InvoiceItem.objects.aggregate(
        total=Sum("quantity")
    )["total"] or 0



    top_products = InvoiceItem.objects.values(
        "product__name"
    ).annotate(
        quantity=Sum("quantity")
    ).order_by(
        "-quantity"
    )[:5]



    context = {
        "today_sales": today_sales,
        "total_invoices": total_invoices,
        "pending_payment": pending_payment,
        "products_sold": products_sold,
        "top_products": top_products,
        "today_expenses": today_expenses,
        "today_profit": today_profit,
    }


    return render(
        request,
        "billing/dashboard.html",
        context
    )

    

def cart_view(request):

    cart = request.session.get("cart", {})

    subtotal = 0


    for item in cart.values():

        item["total"] = (
            item["price"] *
            item["quantity"]
        )

        subtotal += item["total"]


    context = {
        "cart": cart,
        "subtotal": subtotal,
    }


    return render(
        request,
        "billing/cart.html",
        context
    )


def add_to_cart(request, product_id):

    product = get_object_or_404(
        Product,
        id=product_id
    )


    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product.id)


    # Check if product already exists in cart

    if product_id in cart:


        if cart[product_id]["quantity"] < product.stock:

            cart[product_id]["quantity"] += 1


        else:

            messages.error(
                request,
                "Not enough stock available"
            )

            return redirect(
                "billing_products"
            )


    else:


        if product.stock > 0:

            cart[product_id] = {

                "name": product.name,

                "price": Decimal(str(product.price)),

                "quantity": 1,

            }


        else:

            messages.error(
                request,
                "Product is out of stock"
            )

            return redirect(
                "billing_products"
            )



    request.session["cart"] = cart


    return redirect(
        "cart"
    )




def remove_from_cart(request, product_id):

    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product_id)


    if product_id in cart:

        del cart[product_id]


    request.session["cart"] = cart


    return redirect("cart")




def remove_from_cart(request, product_id):

    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product_id)


    if product_id in cart:

        del cart[product_id]


    request.session["cart"] = cart


    return redirect("cart")




def increase_quantity(request, product_id):

    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product_id)


    if product_id in cart:

        cart[product_id]["quantity"] += 1


    request.session["cart"] = cart


    return redirect("cart")




def decrease_quantity(request, product_id):

    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product_id)


    if product_id in cart:


        if cart[product_id]["quantity"] > 1:

            cart[product_id]["quantity"] -= 1


        else:

            del cart[product_id]


    request.session["cart"] = cart


    return redirect("cart")


def clear_cart(request):

    request.session["cart"] = {}

    return redirect("cart")



@login_required
def checkout(request):

    cart = request.session.get(
        "cart",
        {}
    )


    if not cart:

        return redirect("cart")



    subtotal = sum(
        item["price"] * item["quantity"]
        for item in cart.values()
    )


    discount = Decimal(
        request.POST.get(
            "discount",
            0
        )
    )


    tax_rate = Decimal(
        request.POST.get(
            "tax",
            0
        )
    )


    tax = (
        subtotal * tax_rate
    ) / 100


    total = (
        subtotal
        - discount
        + tax
    )

    paid_amount = Decimal(
        request.POST.get(
            "paid_amount",
            0
        )
    )


    due_amount = total - paid_amount



    if due_amount <= 0:

        payment_status = "paid"

        due_amount = 0


    elif paid_amount > 0:

        payment_status = "partial"


    else:

        payment_status = "due"


    if request.method == "POST":
        with transaction.atomic():
        
            customer_id = request.POST.get(
                "customer"
            )


            customer = None


            if customer_id:

                customer = Customer.objects.get(
                    id=customer_id
                )



            invoice = Invoice.objects.create(

                invoice_number=f"INV-{Invoice.objects.count()+1:05d}",

                customer=customer,

                created_by=request.user,


                subtotal=subtotal,

                discount=discount,

                tax=tax,

                total=total,


                paid_amount=paid_amount,

                due_amount=due_amount,


                payment_status=payment_status,


                payment_method=request.POST.get(
                    "payment_method"
                )

            )



        for product_id, item in cart.items():


            product = Product.objects.get(
                id=product_id
            )


            quantity = item["quantity"]


            # Stock check

            if product.stock < quantity:

                messages.error(
                    request,
                    f"{product.name} does not have enough stock."
                )

                invoice.delete()

                return redirect(
                    "checkout"
                )


            InvoiceItem.objects.create(

                invoice=invoice,

                product=product,

                quantity=quantity,

                price=item["price"],

                total=item["price"] * quantity

            )


            # Reduce stock

            product.stock -= quantity

            product.save()



        request.session["cart"] = {}



        return redirect(
            "invoice",
            invoice.id
        )



    context = {

        "cart":cart,

        "subtotal":subtotal,

        "customers":Customer.objects.all()

    }


    return render(
        request,
        "billing/checkout.html",
        context
    )




@login_required
def invoice_detail(request, id):

    invoice = get_object_or_404(
        Invoice,
        id=id
    )


    context = {

        "invoice": invoice,

    }


    return render(
        request,
        "billing/invoice.html",
        context
    )



@login_required
def billing_products(request):

    query = request.GET.get(
        "q",
        ""
    )


    products = Product.objects.all()


    if query:

        products = products.filter(
            Q(name__icontains=query)
            |
            Q(category__name__icontains=query)
        )


    context = {

        "products": products,

        "query": query,

    }


    return render(
        request,
        "billing/products.html",
        context
    )


@login_required
def customers(request):

    customers = Customer.objects.all()


    return render(
        request,
        "billing/customers.html",
        {
            "customers": customers
        }
    ) 



@login_required
def add_customer(request):


    if request.method == "POST":
        with transaction.atomic():

            Customer.objects.create(

                name=request.POST.get(
                    "name"
                ),

                phone=request.POST.get(
                    "phone"
                ),

                email=request.POST.get(
                    "email"
                ),

                address=request.POST.get(
                    "address"
                )

            )


        messages.success(
            request,
            "Customer added successfully"
        )


        return redirect(
            "customers"
        )


    return render(
        request,
        "billing/add_customer.html"
    )


@login_required
def customer_detail(request, id):

    customer = get_object_or_404(
        Customer,
        id=id
    )


    invoices = Invoice.objects.filter(
        customer=customer
    ).order_by(
        "-created_at"
    )


    total_purchase = invoices.aggregate(
        total=Sum("total")
    )["total"] or 0



    total_paid = invoices.aggregate(
        total=Sum("paid_amount")
    )["total"] or 0



    total_due = invoices.aggregate(
        total=Sum("due_amount")
    )["total"] or 0



    context = {


        "customer": customer,

        "invoices": invoices,

        "total_purchase": total_purchase,

        "total_paid": total_paid,

        "total_due": total_due,


    }


    return render(
        request,
        "billing/customer_detail.html",
        context
    )




@login_required
def expenses(request):

    expenses = Expense.objects.all().order_by(
        "-created_at"
    )


    return render(
        request,
        "billing/expenses.html",
        {
            "expenses": expenses
        }
    )




@login_required
def add_expense(request):

    if request.method == "POST":
        with transaction.atomic():

            Expense.objects.create(

                title=request.POST.get(
                    "title"
                ),

                expense_type=request.POST.get(
                    "expense_type"
                ),

                amount=request.POST.get(
                    "amount"
                ),

                description=request.POST.get(
                    "description"
                )

            )


        messages.success(
            request,
            "Expense added successfully"
        )


        return redirect(
            "expenses"
        )


    return render(
        request,
        "billing/add_expense.html"
    )


@login_required
def sales_report(request):

    invoices = Invoice.objects.all().order_by(
        "-created_at"
    )


    start_date = request.GET.get(
        "start_date"
    )

    end_date = request.GET.get(
        "end_date"
    )


    if start_date and end_date:

        invoices = invoices.filter(

            created_at__date__range=[
                start_date,
                end_date
            ]

        )



    total_sales = invoices.aggregate(
        total=Sum("total")
    )["total"] or 0



    total_paid = invoices.aggregate(
        total=Sum("paid_amount")
    )["total"] or 0



    total_due = invoices.aggregate(
        total=Sum("due_amount")
    )["total"] or 0



    context = {

        "invoices": invoices,

        "total_sales": total_sales,

        "total_paid": total_paid,

        "total_due": total_due,

        "start_date": start_date,

        "end_date": end_date,

    }


    return render(
        request,
        "billing/sales_report.html",
        context
    )



@login_required
def export_sales_csv(request):

    invoices = filter_invoices_by_date(request)


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
            "Date"
        ]
    )


    for invoice in invoices:


        customer = (
            invoice.customer.name
            if invoice.customer
            else "Walk-in"
        )


        writer.writerow(
            [
                invoice.invoice_number,
                customer,
                invoice.total,
                invoice.paid_amount,
                invoice.due_amount,
                invoice.created_at.strftime(
                    "%Y-%m-%d"
                )
            ]
        )


    return response


@login_required
def export_sales_pdf(request):

    invoices = filter_invoices_by_date(request)



    response = HttpResponse(
        content_type="application/pdf"
    )


    response["Content-Disposition"] = (
        'attachment; filename="sales_report.pdf"'
    )



    pdf = canvas.Canvas(response)



    pdf.setFont(
        "Helvetica-Bold",
        18
    )


    pdf.drawString(
        50,
        800,
        "POS SALES REPORT"
    )



    y = 760



    pdf.setFont(
        "Helvetica",
        12
    )



    for invoice in invoices:


        customer = (
            invoice.customer.name
            if invoice.customer
            else "Walk-in"
        )


        line = (
            f"{invoice.invoice_number} "
            f"{customer} "
            f"Rs {invoice.total}"
        )


        pdf.drawString(
            50,
            y,
            line
        )


        y -= 25



        if y < 50:

            pdf.showPage()

            y = 800



    pdf.save()


    return response


def filter_invoices_by_date(request):

    invoices = Invoice.objects.all().order_by(
        "-created_at"
    )


    start_date = request.GET.get(
        "start_date"
    )

    end_date = request.GET.get(
        "end_date"
    )


    if start_date and end_date:

        invoices = invoices.filter(
            created_at__date__range=[
                start_date,
                end_date
            ]
        )


    return invoices


@login_required
def scan_barcode(request, barcode):

    product = get_object_or_404(
        Product,
        barcode=barcode
    )


    cart = request.session.get(
        "cart",
        {}
    )


    product_id = str(product.id)


    if product_id in cart:

        cart[product_id]["quantity"] += 1

    else:

        cart[product_id] = {

            "name": product.name,

            "price": str(product.price),

            "quantity": 1

        }


    request.session["cart"] = cart


    messages.success(
        request,
        f"{product.name} added to cart"
    )


    return redirect(
        "billing_products"
    )
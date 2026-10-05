import csv
import logging
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.pdfgen import canvas

from inventory.models import Product
from django.db.models.functions import TruncDate
from .models import Customer, Expense, Invoice, InvoiceItem

logger = logging.getLogger(__name__)
CART_KEY = "cart"

@login_required
def sales_dashboard(request):

    today = timezone.now().date()


    today_invoices = Invoice.objects.filter(
        created_at__date=today
    )


    today_sales = today_invoices.aggregate(
        total=Sum("total")
    )["total"] or Decimal("0.00")



    today_expenses = Expense.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    today_profit = (
        today_sales -
        today_expenses
    )



    total_invoices = Invoice.objects.count()



    pending_payment = Invoice.objects.filter(
        due_amount__gt=0
    ).aggregate(
        total=Sum("due_amount")
    )["total"] or Decimal("0.00")



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



    low_stock_products = Product.objects.filter(
        stock__lte=5
    ).order_by(
        "stock"
    )


        # Last 7 days sales

    last_7_days = (
        Invoice.objects
        .filter(
            created_at__date__gte=today - timedelta(days=6)
        )
        .annotate(
            date=TruncDate("created_at")
        )
        .values("date")
        .annotate(
            total=Sum("total")
        )
        .order_by("date")
    )



    sales_labels = []

    sales_values = []


    for sale in last_7_days:

        sales_labels.append(
            sale["date"].strftime("%a")
        )

        sales_values.append(
            float(sale["total"])
        )





    # Payment methods

    payment_data = (
        Invoice.objects
        .values("payment_method")
        .annotate(
            total=Sum("total")
        )
    )



    payment_labels = []

    payment_values = []


    for payment in payment_data:

        payment_labels.append(
            payment["payment_method"]
        )

        payment_values.append(
            float(payment["total"])
        )


    recent_invoices = Invoice.objects.select_related(
        "customer"
    ).order_by(
        "-created_at"
    )[:5]



    context = {

        "today_sales": today_sales,

        "total_invoices": total_invoices,

        "pending_payment": pending_payment,

        "products_sold": products_sold,

        "top_products": top_products,

        "today_expenses": today_expenses,

        "today_profit": today_profit,

        "low_stock_products": low_stock_products,

        "recent_invoices": recent_invoices,
        "sales_labels": sales_labels,

        "sales_values": sales_values,

        "payment_labels": payment_labels,

        "payment_values": payment_values,
    }



    return render(
        request,
        "billing/dashboard.html",
        context
    )


def _get_cart(request):

    return request.session.get(CART_KEY, {})


def _save_cart(request, cart):
    request.session[CART_KEY] = cart
    request.session.modified = True


def _cart_lines(cart):
    """Return ({product_id: line}, subtotal) using Decimal arithmetic.

    Used for *display*.  Checkout recomputes prices from the database.
    """
    lines = {}
    subtotal = Decimal("0")

    for product_id, item in cart.items():
        price = Decimal(str(item["price"]))
        quantity = int(item["quantity"])
        total = price * quantity

        lines[product_id] = {
            "name": item["name"],
            "price": price,
            "quantity": quantity,
            "total": total,
        }
        subtotal += total

    return lines, subtotal


def _add_product(cart, product):
    """Add one unit of `product` to `cart` (mutates it).

    Returns None on success, or an error message string.
    """
    key = str(product.id)
    in_cart = cart[key]["quantity"] if key in cart else 0

    if product.stock <= 0:
        return f"{product.name} is out of stock."

    if in_cart + 1 > product.stock:
        return f"Not enough stock for {product.name} (only {product.stock} left)."

    if key in cart:
        cart[key]["quantity"] += 1
    else:
        cart[key] = {
            "name": product.name,
            "price": str(product.price),
            "quantity": 1,
        }

    return None


@login_required
def cart_view(request):
    lines, subtotal = _cart_lines(_get_cart(request))

    return render(
        request,
        "billing/cart.html",
        {"cart": lines, "subtotal": subtotal},
    )


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    cart = _get_cart(request)

    error = _add_product(cart, product)

    if error:
        messages.error(request, error)
    else:
        _save_cart(request, cart)
        messages.success(
            request,
            f"{product.name} added to cart."
        )

    return redirect("cart")


@login_required
@require_POST
def remove_from_cart(request, product_id):
    cart = _get_cart(request)
    cart.pop(str(product_id), None)
    _save_cart(request, cart)
    return redirect("cart")


@login_required
@require_POST
def increase_quantity(request, product_id):
    cart = _get_cart(request)
    key = str(product_id)

    if key in cart:
        product = Product.objects.filter(id=product_id).first()

        if product is None:
            del cart[key]
            messages.error(request, "That product no longer exists.")
        else:
            error = _add_product(cart, product)
            if error:
                messages.error(request, error)

        _save_cart(request, cart)

    return redirect("cart")


@login_required
@require_POST
def decrease_quantity(request, product_id):
    cart = _get_cart(request)
    key = str(product_id)

    if key in cart:
        if cart[key]["quantity"] > 1:
            cart[key]["quantity"] -= 1
        else:
            del cart[key]

        _save_cart(request, cart)

    return redirect("cart")


@login_required
@require_POST
def clear_cart(request):
    _save_cart(request, {})
    return redirect("cart")


# --------------------------------------------------------------------------
# Checkout
# --------------------------------------------------------------------------

TWO_PLACES = Decimal("0.01")


class CheckoutError(Exception):
    """A problem the cashier can fix (bad input, not enough stock...).

    The message is shown to the user.  Raising it inside transaction.atomic()
    rolls back everything done so far.
    """


def _parse_money(raw, label):
    """Parse a non-negative, finite decimal from form input ('' -> 0)."""
    raw = (raw or "").strip()
    if raw == "":
        return Decimal("0")

    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise CheckoutError(f"{label} must be a valid number.")

    if not value.is_finite():
        raise CheckoutError(f"{label} must be a valid number.")

    if value < 0:
        raise CheckoutError(f"{label} cannot be negative.")

    return value


def _create_invoice(request, cart):
    """Validate the POST data and create the invoice.  Raises CheckoutError.

    Must be called inside transaction.atomic().  Product rows are locked with
    select_for_update(), so two cashiers selling the last unit at the same
    moment cannot both succeed.
    """
    # 1. Parse and validate the form fields (no DB writes yet).
    discount = _parse_money(request.POST.get("discount"), "Discount")
    tax_rate = _parse_money(request.POST.get("tax"), "Tax %")
    paid_amount = _parse_money(request.POST.get("paid_amount"), "Paid amount")

    if tax_rate > 100:
        raise CheckoutError("Tax % cannot be more than 100.")

    payment_method = request.POST.get("payment_method")
    if payment_method not in dict(Invoice.PAYMENT_METHODS):
        raise CheckoutError("Please choose a valid payment method.")

    customer = None
    customer_id = request.POST.get("customer")
    if customer_id:
        if not customer_id.isdigit():
            raise CheckoutError("Please choose a valid customer.")
        customer = Customer.objects.filter(id=customer_id).first()
        if customer is None:
            raise CheckoutError("That customer no longer exists.")

    # 2. Lock the products (in id order, to avoid deadlocks) and check stock.
    product_ids = sorted(int(pid) for pid in cart)
    products = {
        p.id: p
        for p in Product.objects.select_for_update()
        .filter(id__in=product_ids)
        .order_by("id")
    }

    items = []
    subtotal = Decimal("0")

    for pid in product_ids:
        quantity = int(cart[str(pid)]["quantity"])
        product = products.get(pid)

        if product is None:
            raise CheckoutError(f"{cart[str(pid)]['name']} no longer exists.")

        if quantity <= 0:
            raise CheckoutError(f"Invalid quantity for {product.name}.")

        if product.stock < quantity:
            raise CheckoutError(
                f"Not enough stock for {product.name} (only {product.stock} left)."
            )

        # Price comes from the database, not from the session, so a stale
        # cart can never be sold at an old price.
        line_total = product.price * quantity
        subtotal += line_total
        items.append((product, quantity, line_total))

    # 3. Totals.
    if discount > subtotal:
        raise CheckoutError("Discount cannot be more than the subtotal.")

    tax = (subtotal * tax_rate / 100).quantize(TWO_PLACES)
    total = subtotal - discount + tax

    # Anything paid over the total is change handed back, not revenue.
    paid_amount = min(paid_amount, total)
    due_amount = total - paid_amount

    if due_amount == 0:
        payment_status = "paid"
    elif paid_amount > 0:
        payment_status = "partial"
    else:
        payment_status = "due"

    # 4. Write.  The invoice number is derived from the primary key, which
    #    the database guarantees is unique -- counting rows (the old
    #    approach) breaks as soon as an invoice is deleted or two requests
    #    overlap.  A random placeholder satisfies the unique constraint for
    #    the instant before we know the pk.
    invoice = Invoice.objects.create(
        invoice_number=f"TMP-{uuid.uuid4().hex}",
        customer=customer,
        created_by=request.user,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        total=total,
        paid_amount=paid_amount,
        due_amount=due_amount,
        payment_status=payment_status,
        payment_method=payment_method,
    )
    invoice.invoice_number = f"INV-{invoice.pk:05d}"
    invoice.save(update_fields=["invoice_number"])

    InvoiceItem.objects.bulk_create(
        [
            InvoiceItem(
                invoice=invoice,
                product=product,
                quantity=quantity,
                price=product.price,
                total=line_total,
            )
            for product, quantity, line_total in items
        ]
    )

    for product, quantity, _ in items:
        product.stock -= quantity
        product.save(update_fields=["stock", "updated_at"])

    return invoice


@login_required
def checkout(request):

    cart = _get_cart(request)

    if not isinstance(cart, dict):
        cart = {}

    if not cart:
        return redirect("cart")


    if request.method == "POST":

        try:

            with transaction.atomic():
                invoice = _create_invoice(request, cart)


        except CheckoutError as error:

            messages.error(request, str(error))
            return redirect("checkout")


        except Exception:

            logger.exception(
                "Unexpected error during checkout (user=%s)",
                request.user.id
            )

            messages.error(
                request,
                "Something went wrong completing the sale. Please try again."
            )

            return redirect("checkout")


        _save_cart(request, {})

        messages.success(
            request,
            f"Invoice {invoice.invoice_number} created successfully."
        )

        return redirect(
            "invoice_detail",
            id=invoice.id
        )


    lines, subtotal = _cart_lines(cart)


    return render(
        request,
        "billing/checkout.html",
        {
            "cart": lines,
            "subtotal": subtotal,
            "customers": Customer.objects.all(),
        },
    )



@login_required
def invoice_detail(request, id):

    invoice = get_object_or_404(
        Invoice,
        id=id
    )


    auto_print = request.GET.get("print") == "true"


    context = {

        "invoice": invoice,
        "auto_print": auto_print,

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
@require_POST
def scan_barcode(request):
    barcode = (request.POST.get("barcode") or "").strip()

    if not barcode:
        messages.error(request, "Please scan or type a barcode.")
        return redirect("billing_products")

    product = Product.objects.filter(barcode=barcode).first()

    if product is None:
        messages.error(request, f"No product found for barcode {barcode}.")
        return redirect("billing_products")

    cart = _get_cart(request)
    error = _add_product(cart, product)

    if error:
        messages.error(request, error)
    else:
        _save_cart(request, cart)
        messages.success(request, f"{product.name} added to cart")

    return redirect("billing_products")
import csv
import logging
import uuid
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count, Avg
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.pdfgen import canvas

from inventory.models import Product
from django.db.models.functions import TruncDate
from .models import Customer, Expense, Invoice, InvoiceItem, ShopSetting, ExpenseCategory

logger = logging.getLogger(__name__)


from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import mm
from reportlab.lib import colors

from django.db.models.functions import TruncMonth

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



CART_KEY = "cart"


def _get_cart(request):
    return request.session.get(CART_KEY, {})


def _save_cart(request, cart):
    request.session[CART_KEY] = cart
    request.session.modified = True


def _add_product(cart, product):
    key = str(product.id)

    current_quantity = int(
        cart.get(key, {}).get("quantity", 0)
    )

    if product.stock <= 0:
        return f"{product.name} is out of stock."

    if current_quantity >= product.stock:
        return (
            f"Not enough stock for {product.name}. "
            f"Only {product.stock} available."
        )

    if key in cart:
        cart[key]["quantity"] = current_quantity + 1
    else:
        cart[key] = {
            "name": product.name,
            "price": str(product.price),
            "quantity": 1,
        }

    return None


@login_required
def billing_products(request):
    query = request.GET.get("q", "").strip()

    products = Product.objects.all()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(barcode__icontains=query)
        )

    cart = _get_cart(request)

    subtotal = Decimal("0.00")

    for item in cart.values():
        price = Decimal(str(item["price"]))
        quantity = int(item["quantity"])

        item["total"] = price * quantity

        subtotal += item["total"]

    return render(
        request,
        "billing/products.html",
        {
            "products": products,
            "query": query,
            "cart": cart,
            "subtotal": subtotal,
        },
    )


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
    )

    cart = _get_cart(request)

    error = _add_product(cart, product)

    if error:
        messages.error(request, error)
    else:
        _save_cart(request, cart)
        messages.success(
            request,
            f"{product.name} added to cart.",
        )

    return redirect("billing_products")


@login_required
def increase_quantity(request, product_id):
    product = get_object_or_404(
        Product,
        id=product_id,
    )

    cart = _get_cart(request)
    key = str(product_id)

    if key not in cart:
        return redirect("billing_products")

    quantity = int(cart[key]["quantity"])

    if quantity >= product.stock:
        messages.error(
            request,
            f"Only {product.stock} {product.name} available.",
        )
        return redirect("billing_products")

    cart[key]["quantity"] = quantity + 1

    _save_cart(request, cart)

    return redirect("billing_products")


@login_required
def decrease_quantity(request, product_id):
    cart = _get_cart(request)
    key = str(product_id)

    if key not in cart:
        return redirect("billing_products")

    quantity = int(cart[key]["quantity"])

    if quantity <= 1:
        del cart[key]
    else:
        cart[key]["quantity"] = quantity - 1

    _save_cart(request, cart)

    return redirect("billing_products")


@login_required
def remove_from_cart(request, product_id):
    cart = _get_cart(request)
    key = str(product_id)

    if key in cart:
        del cart[key]
        _save_cart(request, cart)

    return redirect("billing_products")


@login_required
def clear_cart(request):
    request.session[CART_KEY] = {}
    request.session.modified = True

    messages.success(
        request,
        "Cart cleared.",
    )

    return redirect("billing_products")



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


@login_required
def cart_view(request):
    lines, subtotal = _cart_lines(_get_cart(request))

    return render(
        request,
        "billing/cart.html",
        {"cart": lines, "subtotal": subtotal},
    )



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
    return_amount = Decimal("0.00")
    due_amount = Decimal("0.00")


    if paid_amount > total:
        return_amount = paid_amount - total

    elif paid_amount < total:
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
        invoice_number=invoice_number,
        customer=customer,
        created_by=request.user,
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        vat=vat,
        total=total,
        paid_amount=paid_amount,
        due_amount=due_amount,
        return_amount=return_amount,
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
def payment(request):

    invoice_data = request.session.get("pending_invoice")

    if not invoice_data:
        messages.error(
            request,
            "No pending payment found."
        )
        return redirect("cart")


    if request.method == "POST":

        paid_amount = Decimal(
            request.POST.get(
                "paid_amount",
                "0"
            )
        )

        return_amount = Decimal("0.00")

        if paid_amount > total:
                return_amount = paid_amount - total


        total = Decimal(
            invoice_data["total"]
        )


        if paid_amount > total:
            paid_amount = total


        due_amount = total - paid_amount


        if due_amount == 0:
            status = "paid"

        elif paid_amount > 0:
            status = "partial"

        else:
            status = "due"



        invoice = Invoice.objects.create(

            invoice_number=invoice_data["invoice_number"],

            customer_id=invoice_data["customer_id"],

            created_by=request.user,

            subtotal=invoice_data["subtotal"],

            discount=invoice_data["discount"],

            tax=invoice_data["tax"],

            vat=invoice_data["vat"],

            total=total,

            paid_amount=paid_amount,

            due_amount=due_amount,

            payment_status=status,

            payment_method=request.POST.get(
                "payment_method",
                "cash"
            )

        )


        for item in invoice_data["items"]:

            product = Product.objects.get(
                id=item["product_id"]
            )


            InvoiceItem.objects.create(

                invoice=invoice,

                product=product,

                quantity=item["quantity"],

                price=item["price"],

                total=item["total"]

            )


            product.stock -= item["quantity"]

            product.save()



        request.session.pop(
            "pending_invoice",
            None
        )


        messages.success(
            request,
            "Payment completed successfully."
        )


        return redirect(
            f"/billing/invoice/{invoice.id}/?print=true"
        )


    return render(
        request,
        "billing/payment.html",
        {
            "invoice": invoice_data
        }
    )



@login_required
def invoice(request, id):

    invoice = get_object_or_404(
        Invoice,
        id=id
    )


    return_amount = Decimal("0.00")


    if invoice.paid_amount > invoice.total:
        return_amount = (
            invoice.paid_amount -
            invoice.total
        )


    return render(
        request,
        "billing/invoice.html",
        {
            "invoice": invoice,
            "return_amount": invoice.return_amount or 0,
        }
    )



@login_required
def checkout(request):
    cart = _get_cart(request)

    if not cart:
        messages.warning(request, "Your cart is empty.")
        return redirect("billing_products")

    # ---------------------------------------------------------
    # Calculate subtotal
    # ---------------------------------------------------------
    subtotal = sum(
        (
            Decimal(str(item["price"])) * int(item["quantity"])
            for item in cart.values()
        ),
        Decimal("0.00"),
    )

    # Calculate line totals for template
    for item in cart.values():
        item["total"] = (
            Decimal(str(item["price"]))
            * int(item["quantity"])
        )

    customers = Customer.objects.all().order_by("name")

    # ---------------------------------------------------------
    # Default values
    # ---------------------------------------------------------
    discount = Decimal("0.00")
    tax_percent = Decimal("0.00")
    vat_percent = Decimal("13.00")

    tax = Decimal("0.00")
    vat = Decimal("0.00")

    total = subtotal
    paid_amount = Decimal("0.00")
    due_amount = Decimal("0.00")

    payment_status = "due"
    payment_method = "cash"

    # ---------------------------------------------------------
    # POST - complete sale
    # ---------------------------------------------------------
    if request.method == "POST":

        customer_id = request.POST.get("customer")

        payment_method = request.POST.get(
            "payment_method",
            "cash",
        )

        # -----------------------------------------------------
        # Parse discount
        # -----------------------------------------------------
        try:
            discount = Decimal(
                request.POST.get("discount", "0") or "0"
            )
        except (TypeError, ValueError, InvalidOperation):
            discount = Decimal("0.00")

        # -----------------------------------------------------
        # Parse tax percentage
        # -----------------------------------------------------
        try:
            tax_percent = Decimal(
                request.POST.get("tax", "0") or "0"
            )
        except (TypeError, ValueError, InvalidOperation):
            tax_percent = Decimal("0.00")

        # -----------------------------------------------------
        # Parse VAT percentage
        # -----------------------------------------------------
        try:
            vat_percent = Decimal(
                request.POST.get("vat", "13") or "13"
            )
        except (TypeError, ValueError, InvalidOperation):
            vat_percent = Decimal("13.00")

        # -----------------------------------------------------
        # Parse paid amount
        # -----------------------------------------------------
        try:
            paid_amount = Decimal(
                request.POST.get("paid_amount", "0") or "0"
            )
        except (TypeError, ValueError, InvalidOperation):
            paid_amount = Decimal("0.00")

        # -----------------------------------------------------
        # Prevent negative values
        # -----------------------------------------------------
        discount = max(
            discount,
            Decimal("0.00"),
        )

        tax_percent = max(
            tax_percent,
            Decimal("0.00"),
        )

        vat_percent = max(
            vat_percent,
            Decimal("0.00"),
        )

        paid_amount = max(
            paid_amount,
            Decimal("0.00"),
        )

        # -----------------------------------------------------
        # Validate percentages
        # -----------------------------------------------------
        if tax_percent > Decimal("100"):
            messages.error(
                request,
                "Tax percentage cannot be more than 100%.",
            )
            return render(
                request,
                "billing/checkout.html",
                {
                    "cart": cart,
                    "customers": customers,
                    "subtotal": subtotal,
                    "discount": discount,
                    "tax": tax,
                    "tax_percent": tax_percent,
                    "vat": vat,
                    "vat_percent": vat_percent,
                    "total": total,
                    "paid_amount": paid_amount,
                    "due_amount": due_amount,
                },
            )

        if vat_percent > Decimal("100"):
            messages.error(
                request,
                "VAT percentage cannot be more than 100%.",
            )
            return render(
                request,
                "billing/checkout.html",
                {
                    "cart": cart,
                    "customers": customers,
                    "subtotal": subtotal,
                    "discount": discount,
                    "tax": tax,
                    "tax_percent": tax_percent,
                    "vat": vat,
                    "vat_percent": vat_percent,
                    "total": total,
                    "paid_amount": paid_amount,
                    "due_amount": due_amount,
                },
            )

        # -----------------------------------------------------
        # Discount cannot exceed subtotal
        # -----------------------------------------------------
        if discount > subtotal:
            discount = subtotal

        # -----------------------------------------------------
        # Taxable amount
        # -----------------------------------------------------
        taxable_amount = subtotal - discount

        # -----------------------------------------------------
        # Calculate tax
        # -----------------------------------------------------
        tax = (
            taxable_amount
            * tax_percent
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # Calculate VAT
        # -----------------------------------------------------
        vat = (
            taxable_amount
            * vat_percent
            / Decimal("100")
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # Final total
        # -----------------------------------------------------
        total = (
            taxable_amount
            + tax
            + vat
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # Payment cannot exceed total
        # -----------------------------------------------------
        if paid_amount > total:
            paid_amount = total

        # -----------------------------------------------------
        # Calculate due
        # -----------------------------------------------------
        due_amount = (
            total - paid_amount
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # Payment status
        # -----------------------------------------------------
        if due_amount == Decimal("0.00"):
            payment_status = "paid"

        elif paid_amount > Decimal("0.00"):
            payment_status = "partial"

        else:
            payment_status = "due"

        # -----------------------------------------------------
        # Validate payment method
        # -----------------------------------------------------
        valid_payment_methods = dict(
            Invoice.PAYMENT_METHODS
        )

        if payment_method not in valid_payment_methods:
            messages.error(
                request,
                "Please select a valid payment method.",
            )

            return render(
                request,
                "billing/checkout.html",
                {
                    "cart": cart,
                    "customers": customers,
                    "subtotal": subtotal,
                    "discount": discount,
                    "tax": tax,
                    "tax_percent": tax_percent,
                    "vat": vat,
                    "vat_percent": vat_percent,
                    "total": total,
                    "paid_amount": paid_amount,
                    "due_amount": due_amount,
                },
            )

        # -----------------------------------------------------
        # Validate customer
        # -----------------------------------------------------
        customer = None

        if customer_id:
            customer = get_object_or_404(
                Customer,
                id=customer_id,
            )

        # -----------------------------------------------------
        # Create invoice + invoice items + stock update
        # -----------------------------------------------------
        with transaction.atomic():

            # Create invoice first.
            invoice_number = (
                f"INV-{Invoice.objects.count() + 1:05d}"
            )

            invoice = Invoice.objects.create(
                invoice_number=invoice_number,
                customer=customer,
                created_by=request.user,
                subtotal=subtotal,
                discount=discount,
                tax=tax,
                vat=vat,
                total=total,
                paid_amount=paid_amount,
                due_amount=due_amount,
                payment_status=payment_status,
                payment_method=payment_method,
            )

            # -------------------------------------------------
            # Create invoice items
            # -------------------------------------------------
            for product_id, item in cart.items():

                product = get_object_or_404(
                    Product.objects.select_for_update(),
                    id=product_id,
                )

                quantity = int(
                    item["quantity"]
                )

                # Final stock validation while row is locked.
                if product.stock < quantity:
                    messages.error(
                        request,
                        f"Not enough stock for {product.name}. "
                        f"Only {product.stock} available.",
                    )

                    raise ValueError(
                        f"Insufficient stock for {product.name}"
                    )

                line_total = (
                    product.price * quantity
                ).quantize(
                    Decimal("0.01")
                )

                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=product,
                    quantity=quantity,
                    price=product.price,
                    total=line_total,
                )

                # Reduce stock.
                product.stock -= quantity

                product.save(
                    update_fields=["stock"]
                )

        # -----------------------------------------------------
        # Clear cart after successful transaction
        # -----------------------------------------------------
        request.session[CART_KEY] = {}
        request.session.modified = True

        messages.success(
            request,
            f"Sale {invoice.invoice_number} completed successfully.",
        )

        return redirect(
            f"/billing/invoice/{invoice.id}/?print=true"
        )

    # ---------------------------------------------------------
    # GET - display checkout page
    # ---------------------------------------------------------
    return render(
        request,
        "billing/checkout.html",
        {
            "cart": cart,
            "customers": customers,

            "subtotal": subtotal,

            "discount": discount,

            "tax": tax,
            "tax_percent": tax_percent,

            "vat": vat,
            "vat_percent": vat_percent,

            "total": total,

            "paid_amount": paid_amount,
            "due_amount": due_amount,

            "payment_status": payment_status,
            "payment_method": payment_method,
        },
    )

@login_required
def invoice_detail(request, id):
    invoice = get_object_or_404(Invoice, id=id)

    auto_print = request.GET.get("print") == "true"
    shop = ShopSetting.objects.first()
    
    return render(
    request,
        "billing/invoice.html",
        {
            "invoice": invoice,
            "shop": shop,
            "auto_print": auto_print,
            "return_amount": invoice.return_amount or 0,
        }
    )
        

# --------------------------------------------------------------
# CUSTOMER 
# -------------------------------------------------------------

@login_required
def customer_list(request):

    customers = Customer.objects.all().order_by("-created_at")


    search = request.GET.get("search")


    if search:

        customers = customers.filter(
            name__icontains=search
        )


    return render(
        request,
        "billing/customers/list.html",
        {
            "customers": customers
        }
    )


@login_required
def customer_create(request):

    if request.method == "POST":

        customer = Customer.objects.create(

            name=request.POST.get("name"),

            phone=request.POST.get("phone"),

            email=request.POST.get("email"),

            address=request.POST.get("address"),

        )


        messages.success(
            request,
            "Customer added successfully"
        )


        return redirect(
            "customer_list"
        )


    return render(
        request,
        "billing/customers/create.html"
    )



@login_required
def customer_detail(request,id):

    customer = get_object_or_404(
        Customer,
        id=id
    )


    invoices = Invoice.objects.filter(
        customer=customer
    ).order_by("-created_at")


    total_purchase = invoices.aggregate(
        total=Sum("total")
    )["total"] or 0


    total_due = invoices.aggregate(
        due=Sum("due_amount")
    )["due"] or 0


    return render(
        request,
        "billing/customers/detail.html",
        {
            "customer":customer,
            "invoices":invoices,
            "total_purchase":total_purchase,
            "total_due":total_due,
        }
    )



@login_required
def customer_edit(request,id):

    customer = get_object_or_404(
        Customer,
        id=id
    )


    if request.method=="POST":

        customer.name=request.POST.get("name")

        customer.phone=request.POST.get("phone")

        customer.email=request.POST.get("email")

        customer.address=request.POST.get("address")


        customer.save()


        messages.success(
            request,
            "Customer updated"
        )


        return redirect(
            "customer_list"
        )


    return render(
        request,
        "billing/customers/edit.html",
        {
            "customer":customer
        }
    )



@login_required
def customer_delete(request,id):

    customer=get_object_or_404(
        Customer,
        id=id
    )


    customer.delete()


    messages.success(
        request,
        "Customer deleted"
    )


    return redirect(
        "customer_list"
    )



@login_required
def customer_statement_pdf(request,id):

    customer = get_object_or_404(
        Customer,
        id=id
    )


    invoices = Invoice.objects.filter(
        customer=customer
    ).order_by("-created_at")



    response = HttpResponse(
        content_type="application/pdf"
    )


    response["Content-Disposition"] = (
        f'attachment; filename="{customer.name}_statement.pdf"'
    )



    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )


    styles = getSampleStyleSheet()


    elements=[]



    # Header

    elements.append(
        Paragraph(
            "<b>MY SHOP</b><br/>CUSTOMER STATEMENT",
            styles["Title"]
        )
    )


    elements.append(
        Spacer(1,20)
    )



    # Customer info

    customer_data=[

        [
            "Customer",
            customer.name
        ],

        [
            "Phone",
            customer.phone or "-"
        ],

        [
            "Email",
            customer.email or "-"
        ],

    ]



    info_table = Table(
        customer_data
    )


    info_table.setStyle(
        TableStyle([

            (
                "GRID",
                (0,0),
                (-1,-1),
                0.5,
                colors.grey
            ),

            (
                "PADDING",
                (0,0),
                (-1,-1),
                8
            )

        ])
    )



    elements.append(
        info_table
    )


    elements.append(
        Spacer(1,25)
    )




    # Invoice table


    data=[

        [
            "Invoice",
            "Date",
            "Amount",
            "Paid",
            "Due",
            "Status"
        ]

    ]



    for invoice in invoices:

        data.append(

            [

                invoice.invoice_number,

                invoice.created_at.strftime(
                    "%Y-%m-%d"
                ),

                f"Rs {invoice.total}",

                f"Rs {invoice.paid_amount}",

                f"Rs {invoice.due_amount}",

                invoice.payment_status.title(),

            ]

        )



    table = Table(
        data
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
                colors.lightgrey
            ),


            (
                "PADDING",
                (0,0),
                (-1,-1),
                6
            )

        ])

    )


    elements.append(table)



    elements.append(
        Spacer(1,25)
    )



    # Summary


    total_purchase = sum(
        i.total for i in invoices
    )


    total_paid = sum(
        i.paid_amount for i in invoices
    )


    total_due = sum(
        i.due_amount for i in invoices
    )



    summary=[


        [
            "Total Purchase",
            f"Rs {total_purchase}"
        ],


        [
            "Total Paid",
            f"Rs {total_paid}"
        ],


        [
            "Total Due",
            f"Rs {total_due}"
        ],


    ]



    summary_table = Table(
        summary
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
                "PADDING",
                (0,0),
                (-1,-1),
                8
            )

        ])

    )


    elements.append(
        summary_table
    )



    elements.append(
        Spacer(1,30)
    )



    elements.append(

        Paragraph(
            "Thank you for your business.",
            styles["Normal"]
        )

    )



    doc.build(
        elements
    )


    return response



# --------------------------------------------------------------
# EXPENSES
# -------------------------------------------------------------
@login_required
def expense_category_list(request):

    categories = ExpenseCategory.objects.annotate(
        expense_count=Count("expenses"),
        total_amount=Sum("expenses__amount")
    ).order_by(
        "group",
        "name"
    )


    search = request.GET.get("search")

    group = request.GET.get("group")


    if search:

        categories = categories.filter(
            name__icontains=search
        )


    if group:

        categories = categories.filter(
            group=group
        )


    return render(
        request,
        "billing/expenses/categories.html",
        {
            "categories": categories,
        }
    )

    

@login_required
def expense_category_create(request):

    if request.method == "POST":

        name = request.POST.get("name")
        group = request.POST.get("group")


        ExpenseCategory.objects.create(
            name=name,
            group=group
        )


        messages.success(
            request,
            "Category created successfully"
        )


        return redirect(
            "expense_category_list"
        )


    return render(
        request,
        "billing/expenses/category_create.html"
    )



@login_required
def expense_category_edit(request, id):

    category = get_object_or_404(
        ExpenseCategory,
        id=id
    )


    if request.method == "POST":

        category.name = request.POST.get("name")
        category.group = request.POST.get("group")

        category.save()


        messages.success(
            request,
            "Category updated successfully"
        )


        return redirect(
            "expense_category_list"
        )



    return render(
        request,
        "billing/expenses/category_edit.html",
        {
            "category": category
        }
    )


@login_required
def expense_category_delete(request,id):

    category = get_object_or_404(
        ExpenseCategory,
        id=id
    )


    if category.expenses.exists():

        messages.error(
            request,
            "Cannot delete category because expenses exist under this category."
        )

        return redirect(
            "expense_category_list"
        )


    category.delete()


    messages.success(
        request,
        "Category deleted successfully"
    )


    return redirect(
        "expense_category_list"
    )



@login_required
def expense_list(request):

    expenses = Expense.objects.select_related(
        "category"
    ).order_by("-created_at")


    # Filters

    group = request.GET.get("group")
    category_id = request.GET.get("category")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")


    if group:
        expenses = expenses.filter(
            category__group=group
        )


    if category_id:
        expenses = expenses.filter(
            category_id=category_id
        )


    if start_date:
        expenses = expenses.filter(
            created_at__date__gte=start_date
        )


    if end_date:
        expenses = expenses.filter(
            created_at__date__lte=end_date
        )



    # Total

    total_expense = expenses.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    # Group totals

    cinema_total = expenses.filter(
        category__group="cinema"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    canteen_total = expenses.filter(
        category__group="canteen"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    general_total = expenses.filter(
        category__group="general"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")




    # Statistics

    total_count = expenses.count()


    average_expense = expenses.aggregate(
        avg=Avg("amount")
    )["avg"] or Decimal("0.00")




    top_category = expenses.values(
        "category__name"
    ).annotate(
        total=Sum("amount")
    ).order_by(
        "-total"
    ).first()




    # Category summary table

    category_summary = expenses.values(
        "category__name"
    ).annotate(
        total=Sum("amount")
    ).order_by(
        "-total"
    )




    # Monthly chart

    monthly_data = (
        expenses
        .annotate(
            month=TruncMonth("created_at")
        )
        .values("month")
        .annotate(
            total=Sum("amount")
        )
        .order_by("month")
    )



    monthly_labels = [
        item["month"].strftime("%b %Y")
        for item in monthly_data
    ]


    monthly_values = [
        float(item["total"])
        for item in monthly_data
    ]




    # Category chart

    category_chart = (
        expenses.values(
            "category__name"
        )
        .annotate(
            total=Sum("amount")
        )
    )


    category_labels = [
        item["category__name"]
        for item in category_chart
    ]


    category_values = [
        float(item["total"])
        for item in category_chart
    ]




    expense_categories = ExpenseCategory.objects.all()



    context = {


        "expenses": expenses,

        "expense_categories": expense_categories,


        "total_expense": total_expense,


        "cinema_total": cinema_total,

        "canteen_total": canteen_total,

        "general_total": general_total,



        "total_count": total_count,

        "average_expense": average_expense,

        "top_category": top_category,



        "category_summary": category_summary,


        "monthly_labels": json.dumps(monthly_labels),

        "monthly_values": json.dumps(monthly_values),


        "category_labels": json.dumps(category_labels),

        "category_values": json.dumps(category_values),


    }



    return render(
        request,
        "billing/expenses/list.html",
        context
    )




@login_required
def expense_create(request):

    expense_categories = ExpenseCategory.objects.all()


    if request.method == "POST":

        title = request.POST.get("title")
        category_id = request.POST.get("category")
        amount = request.POST.get("amount")
        description = request.POST.get("description")


        category = ExpenseCategory.objects.get(
            id=category_id
        )


        Expense.objects.create(
            title=title,
            category=category,
            amount=amount,
            description=description,
        )


        return redirect("expense_list")



    return render(
        request,
        "billing/expenses/create.html",
        {
            "expense_categories": expense_categories,
        }
    )



@login_required
def expense_edit(request, id):

    expense = get_object_or_404(
        Expense,
        id=id
    )


    expense_categories = ExpenseCategory.objects.all()


    if request.method == "POST":

        title = request.POST.get("title")
        category_id = request.POST.get("category")
        amount = request.POST.get("amount")
        description = request.POST.get("description")


        category = get_object_or_404(
            ExpenseCategory,
            id=category_id
        )


        expense.title = title
        expense.category = category
        expense.amount = Decimal(amount)
        expense.description = description

        expense.save()


        messages.success(
            request,
            "Expense updated successfully."
        )


        return redirect("expense_list")

    return render(
        request,
        "billing/expenses/edit.html",
        {
            "expense": expense,
            "expense_categories": expense_categories,
        }
    )


@login_required
def expense_detail(request, id):

    expense = get_object_or_404(
        Expense.objects.select_related("category"),
        id=id
    )


    context = {

        "expense": expense,

    }


    return render(
        request,
        "billing/expenses/detail.html",
        context
    )

@login_required
def expense_delete(request,id):

    expense=get_object_or_404(
        Expense,
        id=id
    )


    expense.delete()


    messages.success(
        request,
        "Expense deleted"
    )


    return redirect(
        "expense_list"
    )



def get_filtered_expenses(request):

    expenses = Expense.objects.select_related(
        "category"
    ).order_by("-created_at")


    group = request.GET.get("group")
    category_id = request.GET.get("category")
    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")


    if group:
        expenses = expenses.filter(
            category__group=group
        )


    if category_id:
        expenses = expenses.filter(
            category_id=category_id
        )


    if start_date:
        expenses = expenses.filter(
            created_at__date__gte=start_date
        )


    if end_date:
        expenses = expenses.filter(
            created_at__date__lte=end_date
        )


    return expenses




@login_required
def expense_export_csv(request):

    expenses = get_filtered_expenses(request)



    response = HttpResponse(
        content_type="text/csv"
    )

    response["Content-Disposition"] = (
        'attachment; filename="expenses.csv"'
    )



    writer = csv.writer(response)



    writer.writerow(
        [
            "Title",
            "Category",
            "Group",
            "Amount",
            "Date"
        ]
    )



    for expense in expenses:


        writer.writerow(
            [
                expense.title,
                expense.category.name,
                expense.category.get_group_display(),
                expense.amount,
                expense.created_at.strftime("%Y-%m-%d")
            ]
        )



    return response


@login_required
def expense_export_pdf(request):

    expenses = get_filtered_expenses(request)


    total = expenses.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")


    cinema_total = expenses.filter(
        category__group="cinema"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")


    canteen_total = expenses.filter(
        category__group="canteen"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")


    general_total = expenses.filter(
        category__group="general"
    ).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    response = HttpResponse(
        content_type="application/pdf"
    )


    response["Content-Disposition"] = (
        'attachment; filename="expense_report.pdf"'
    )



    doc = SimpleDocTemplate(
        response,
        rightMargin=30,
        leftMargin=30,
        topMargin=40,
        bottomMargin=40,
    )



    elements = []


    styles = getSampleStyleSheet()



    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        alignment=1,
        fontSize=18,
        spaceAfter=10,
    )


    normal = styles["Normal"]



    # Header

    elements.append(
        Paragraph(
            "POS Expense Report",
            title_style
        )
    )


    elements.append(
        Paragraph(
            f"Generated Date: {timezone.now().strftime('%Y-%m-%d')}",
            normal
        )
    )


    elements.append(
        Spacer(1,20)
    )



    # Summary

    summary_data = [

        ["Total Expense", "Cinema Hall", "Canteen", "General"],

        [
            f"Rs {total}",
            f"Rs {cinema_total}",
            f"Rs {canteen_total}",
            f"Rs {general_total}",
        ]

    ]



    summary_table = Table(
        summary_data,
        colWidths=[120,120,120,120]
    )


    summary_table.setStyle(
        TableStyle(
            [
                ("GRID",(0,0),(-1,-1),0.5,None),
                ("ALIGN",(0,0),(-1,-1),"CENTER"),
                ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ]
        )
    )


    elements.append(
        summary_table
    )


    elements.append(
        Spacer(1,25)
    )




    # Expense table

    data = [

        [
            "Title",
            "Category",
            "Group",
            "Amount",
            "Date"
        ]

    ]



    for expense in expenses:


        data.append(

            [
                expense.title,
                expense.category.name,
                expense.category.get_group_display(),
                f"Rs {expense.amount}",
                expense.created_at.strftime("%Y-%m-%d")
            ]

        )



    table = Table(
        data,
        repeatRows=1
    )



    table.setStyle(

        TableStyle(

            [

                ("GRID",(0,0),(-1,-1),0.5,None),

                ("VALIGN",(0,0),(-1,-1),"TOP"),

                ("ALIGN",(3,1),(3,-1),"RIGHT"),

            ]

        )

    )



    elements.append(
        table
    )



    doc.build(elements)



    return response


    
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
    )["total"] or Decimal("0.00")

    total_due = invoices.aggregate(
        total=Sum("due_amount")
    )["total"] or Decimal("0.00")



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


@login_required
def invoice_pdf(request, id):

    invoice = get_object_or_404(
        Invoice,
        id=id
    )


    response = HttpResponse(
        content_type="application/pdf"
    )


    response["Content-Disposition"] = (
        f'attachment; filename="{invoice.invoice_number}.pdf"'
    )


    doc = SimpleDocTemplate(
        response,
        pagesize=(80*mm, 200*mm),
        rightMargin=5*mm,
        leftMargin=5*mm,
        topMargin=5*mm,
        bottomMargin=5*mm,
    )


    styles = getSampleStyleSheet()

    elements = []


    elements.append(
        Paragraph(
            "<b>MY SHOP</b><br/>POS BILLING SYSTEM",
            styles["Title"]
        )
    )


    elements.append(
        Spacer(1,10)
    )


    info = [

        [
            "Invoice",
            invoice.invoice_number
        ],

        [
            "Date",
            invoice.created_at.strftime(
                "%Y-%m-%d %H:%M"
            )
        ],

        [
            "Customer",
            invoice.customer.name
            if invoice.customer
            else "Walk-in"
        ]

    ]


    table = Table(info)


    table.setStyle(
        TableStyle([
            ("GRID",(0,0),(-1,-1),0.2,colors.grey),
            ("FONTSIZE",(0,0),(-1,-1),8),
        ])
    )


    elements.append(table)


    elements.append(
        Spacer(1,10)
    )



    items = [
        [
            "Item",
            "Qty",
            "Total"
        ]
    ]


    for item in invoice.items.all():

        items.append(
            [
                item.product.name,
                item.quantity,
                f"{item.total}"
            ]
        )


    item_table = Table(
        items
    )


    item_table.setStyle(
        TableStyle([
            ("GRID",(0,0),(-1,-1),0.2,colors.grey),
            ("FONTSIZE",(0,0),(-1,-1),8),
        ])
    )


    elements.append(item_table)



    elements.append(
        Spacer(1,10)
    )


    totals = [

        ["Subtotal", invoice.subtotal],

        ["Discount", invoice.discount],

        ["VAT", invoice.vat],

        ["TOTAL", invoice.total],

        ["Paid", invoice.paid_amount],

        ["Return", invoice.return_amount],

        ["Due", invoice.due_amount],

    ]


    total_table = Table(
        totals
    )


    total_table.setStyle(
        TableStyle([
            ("ALIGN",(1,0),(1,-1),"RIGHT"),
            ("FONTSIZE",(0,0),(-1,-1),9),
            ("LINEABOVE",(0,3),(-1,3),1,colors.black),
        ])
    )


    elements.append(total_table)



    elements.append(
        Spacer(1,15)
    )


    elements.append(
        Paragraph(
            "Thank You!<br/>Visit Again",
            styles["Normal"]
        )
    )


    doc.build(elements)


    return response


    
     
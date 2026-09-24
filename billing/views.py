from django.shortcuts import render
from django.shortcuts import render,redirect,get_object_or_404
from inventory.models import Product

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Invoice, InvoiceItem, Customer

from django.db.models import Q

from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta


@login_required
def sales_dashboard(request):

    today = timezone.now().date()


    today_invoices = Invoice.objects.filter(
        created_at__date=today
    )


    today_sales = today_invoices.aggregate(
        total=Sum("total")
    )["total"] or 0



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

                "price": float(product.price),

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


    discount = float(
        request.POST.get(
            "discount",
            0
        )
    )


    tax_rate = float(
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

    paid_amount = float(
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



        for product_id,item in cart.items():


            product = Product.objects.get(
                id=product_id
            )



            InvoiceItem.objects.create(

                invoice=invoice,

                product=product,

                quantity=item["quantity"],

                price=item["price"],

                total=
                item["price"] *
                item["quantity"]

            )



            # Reduce Stock

            product.stock -= item["quantity"]

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

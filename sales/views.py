import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum

from django.shortcuts import redirect, render

from inventory.models import Product
from .models import Sale

logger = logging.getLogger(__name__)


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
    sales = Sale.objects.select_related('product','sold_by').order_by('-id')
    paginator = Paginator(sales, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'sales/history.html', {'page_obj':page_obj})

   



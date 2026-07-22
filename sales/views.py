from django.shortcuts import render, redirect
from .models import Sale
from inventory.models import Product
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.core.paginator import Paginator
from django.db.models import Sum, Count


# Create your views here.
@login_required
def create_sales(request):
    products = Product.objects.filter(is_available=True)

    if request.method == "POST":
        product_id = request.POST.get("product")
        quantity = int(request.POST.get("quantity"))

        product = Product.objects.get(id=product_id)

        if quantity > product.stock:
            messages.error(request, "Not Enough Stock")
            return redirect("sales_dashboard")

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

   



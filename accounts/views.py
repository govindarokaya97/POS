from django.shortcuts import render, redirect
from .forms import RegisterForm, LoginForm
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required


from inventory.models import Category, Product
from sales.models import Sale
from django.db.models import Sum
# Create your views here.

def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, "Account created successfully. Please log in.")
            return redirect("login")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegisterForm()

    context = {
        "form": form
    }
    return render(request, 'accounts/register.html', context)

def login_user(request):
    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Login Successfilly")
            return redirect("dashboard")
    
    else:
        form = LoginForm()

    context={"form":form}
    return render(request, 'accounts/login.html',context)

def logout_user(request):
    logout(request)
    messages.success(request, "Logout Successfilly")
    return redirect("login")



@login_required
def dashboard(request):
    total_categories = Category.objects.count()
    total_products = Product.objects.count()
    total_sales = Sale.objects.count()
    revenue = Sale.objects.aggregate(total=Sum("total_price"))["total"] or 0

    recent_sales = (
        Sale.objects.select_related("product", "sold_by")
        .order_by("-sold_at")[:5]
    )

    low_stock_products = Product.objects.filter(stock__lte=5)

    context = {
        "total_categories": total_categories,
        "total_products": total_products,
        "total_sales": total_sales,
        "revenue": revenue,
        "recent_sales": recent_sales,
        "low_stock_products": low_stock_products,
    }

    return render(request, "accounts/dashboard.html", context)
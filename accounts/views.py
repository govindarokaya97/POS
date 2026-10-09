from django.shortcuts import render, redirect
from .forms import RegisterForm, LoginForm
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST


from inventory.models import Category, Product
from billing.models import Invoice, Expense
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal
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



@require_POST
def logout_user(request):
    logout(request)
    messages.success(request, "Logout Successfilly")
    return redirect("login")



@login_required
def dashboard(request):

    today = timezone.now().date()


    # Inventory
    total_categories = Category.objects.count()

    total_products = Product.objects.count()


    # Invoice sales
    total_invoices = Invoice.objects.count()


    total_revenue = Invoice.objects.aggregate(
        total=Sum("total")
    )["total"] or Decimal("0.00")


    # Today sales

    today_invoices = Invoice.objects.filter(
        created_at__date=today
    )


    today_sales = today_invoices.aggregate(
        total=Sum("total")
    )["total"] or Decimal("0.00")


    today_invoice_count = today_invoices.count()



    # Payment information

    total_paid = Invoice.objects.aggregate(
        total=Sum("paid_amount")
    )["total"] or Decimal("0.00")


    total_due = Invoice.objects.aggregate(
        total=Sum("due_amount")
    )["total"] or Decimal("0.00")



    # Expenses

    total_expense = Expense.objects.aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0.00")



    # Profit estimate

    net_profit = total_revenue - total_expense



    # Recent invoices

    recent_sales = (
        Invoice.objects
        .select_related("customer")
        .order_by("-created_at")[:5]
    )



    # Low stock

    low_stock_products = Product.objects.filter(
        stock__lte=5
    )



    context = {

        "total_categories": total_categories,

        "total_products": total_products,

        "total_sales": total_invoices,

        "revenue": total_revenue,


        "today_sales": today_sales,

        "today_invoice_count": today_invoice_count,

        "total_paid": total_paid,

        "total_due": total_due,

        "total_expense": total_expense,

        "net_profit": net_profit,


        "recent_sales": recent_sales,

        "low_stock_products": low_stock_products,

    }


    return render(
        request,
        "accounts/dashboard.html",
        context
    )

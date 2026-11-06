import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.views.decorators.http import require_POST

from core.permissions import staff_required
from inventory.models import Category, Product
from billing.models import Invoice, Expense

from .forms import RegisterForm, LoginForm

logger = logging.getLogger(__name__)




def send_verification_email(request, user):
    """
    Send a secure email verification link.
    """

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    verification_url = request.build_absolute_uri(
        reverse(
            "verify_email",
            kwargs={
                "uidb64": uid,
                "token": token,
            },
        )
    )

    context = {
        "user": user,
        "verification_url": verification_url,
    }

    subject = "Verify Your POS Account"

    text_content = render_to_string(
        "accounts/emails/verify_email.txt",
        context,
    )

    html_content = render_to_string(
        "accounts/emails/verify_email.html",
        context,
    )

    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )

    email.attach_alternative(html_content, "text/html")
    email.send(fail_silently=False)


# --------------------------------------------------
# PUBLIC REGISTRATION
# --------------------------------------------------

def register(request):

    if request.user.is_authenticated:
        return redirect("pos_home")

    if request.method == "POST":

        form = RegisterForm(request.POST)

        if form.is_valid():

            user = form.save(commit=False)

            # Account cannot log in before email verification.
            user.is_active = False
            user.save()

            form.save_m2m()

            try:
                send_verification_email(request, user)

                messages.success(
                    request,
                    "Registration successful! "
                    "Please check your email to verify your account."
                )

                return redirect("login")

            except Exception:
                logger.exception(
                    "Failed to send verification email for user ID %s",
                    user.pk,
                )

                messages.warning(
                    request,
                    "Your account has been created but the verification "
                    "email could not be sent. Please use the resend "
                    "verification option."
                )

                return redirect("resend_verification")

        messages.error(
            request,
            "Please correct the errors below."
        )

    else:
        form = RegisterForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


# --------------------------------------------------
# VERIFY EMAIL
# --------------------------------------------------



def verify_email(request, uidb64, token):

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)

    except (
        TypeError,
        ValueError,
        OverflowError,
        UnicodeDecodeError,
        User.DoesNotExist,
    ):
        user = None

    if user is None:
        return render(
            request,
            "accounts/email_verification_invalid.html",
        )

    if user.is_active:
        messages.info(
            request,
            "Your email address has already been verified. Please log in."
        )
        return redirect("login")

    if not default_token_generator.check_token(user, token):
        return render(
            request,
            "accounts/email_verification_invalid.html",
        )

    if request.method == "POST":

        user.is_active = True
        user.save(update_fields=["is_active"])

        messages.success(
            request,
            "Email verified successfully! You can now log in."
        )

        return redirect("login")

    return render(
        request,
        "accounts/verify_email.html",
        {"user": user},
    )



# --------------------------------------------------
# RESEND VERIFICATION EMAIL
# --------------------------------------------------

def resend_verification(request):

    if request.method == "POST":

        email = request.POST.get("email", "").strip().lower()

        # Always return the same public response to avoid
        # revealing whether an email address is registered.
        success_message = (
            "If an unverified account exists for that email, "
            "a verification link will be sent."
        )

        user = User.objects.filter(
            email__iexact=email,
            is_active=False,
        ).first()

        if user:
            try:
                send_verification_email(request, user)

            except Exception:
                logger.exception(
                    "Failed to resend verification email for user ID %s",
                    user.pk,
                )

        messages.info(request, success_message)

        return redirect("login")

    return render(
        request,
        "accounts/resend_verification.html",
    )



# --------------------------------------------------
# LOGIN
# --------------------------------------------------

def login_user(request):

    if request.user.is_authenticated:
        return redirect("pos_home")

    if request.method == "POST":
        form = LoginForm(
            request,
            data=request.POST
        )

        if form.is_valid():
            login(request, form.get_user())

            messages.success(
                request,
                "Login successful."
            )

            return redirect("pos_home")

    else:
        form = LoginForm()

    return render(
        request,
        "accounts/login.html",
        {"form": form}
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@require_POST
def logout_user(request):

    logout(request)

    messages.success(
        request,
        "You have been logged out successfully."
    )

    return redirect("login")


# --------------------------------------------------
# DASHBOARD
# Existing dashboard functionality preserved.
# --------------------------------------------------

@staff_required
def dashboard(request):

    today = timezone.now().date()

    # Inventory
    total_categories = Category.objects.count()
    total_products = Product.objects.count()

    # Invoice sales
    total_invoices = Invoice.objects.count()

    total_revenue = (
        Invoice.objects.aggregate(
            total=Sum("total")
        )["total"] or Decimal("0.00")
    )

    # Today's sales
    today_invoices = Invoice.objects.filter(
        created_at__date=today
    )

    today_sales = (
        today_invoices.aggregate(
            total=Sum("total")
        )["total"] or Decimal("0.00")
    )

    today_invoice_count = today_invoices.count()

    # Payment information
    total_paid = (
        Invoice.objects.aggregate(
            total=Sum("paid_amount")
        )["total"] or Decimal("0.00")
    )

    total_due = (
        Invoice.objects.aggregate(
            total=Sum("due_amount")
        )["total"] or Decimal("0.00")
    )

    # Expenses
    total_expense = (
        Expense.objects.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
    )

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

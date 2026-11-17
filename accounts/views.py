import logging
from decimal import Decimal

import csv

from django.http import HttpResponse

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from django.shortcuts import render, redirect,  get_object_or_404
from django.views.decorators.http import require_POST
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import update_session_auth_hash, login, logout
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives

from django.db.models import Sum, Q
from django.core.paginator import Paginator
from django.utils.dateparse import parse_date

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode

from core.permissions import staff_required, superuser_required
from inventory.models import Category, Product
from billing.models import Invoice, Expense
from .models import ActivityLog, UserPreference

from .forms import (
    LoginForm,
    RegisterForm,
    ProfileForm,
    UserManagementForm,
    UserEditForm,
)

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

    if request.user.is_authenticated and not request.user.is_superuser:
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

    if request.user.is_authenticated and not request.user.is_superuser:
        return redirect("pos_home")

    if request.method == "POST":
        form = LoginForm(
            request,
            data=request.POST
        )

        if form.is_valid():
            authenticated_user = form.get_user()
            login(request, authenticated_user)

            record_activity(
                request,
                action="login",
                description=f"User '{authenticated_user.username}' logged in.",
                target_user=authenticated_user,
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

    if request.user.is_authenticated:
        logged_out_user = request.user

        record_activity(
            request,
            action="logout",
            description=f"User '{logged_out_user.username}' logged out.",
            target_user=logged_out_user,
        )

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



# --------------------------------------------------
# MY PROFILE
# --------------------------------------------------

@login_required
def profile(request):
    user = request.user

    preference, created = UserPreference.objects.get_or_create(
        user=user,
        defaults={"theme": "system"},
    )

    return render(request, "accounts/profile.html", {
        "profile_user": user,
        "preference": preference,
    })



# --------------------------------------------------
# EDIT PROFILE
# --------------------------------------------------
@login_required
def edit_profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Your profile was updated successfully."
            )
            return redirect("profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "accounts/edit_profile.html", {
        "form": form,
    })



@login_required
def my_profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)

        if form.is_valid():
            form.save()
            messages.success(request, "Your profile was updated successfully.")
            return redirect("my_profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "accounts/profile.html", {
        "form": form,
    })




# --------------------------------------------------
# DEACTIVATE ACCOUNT
# --------------------------------------------------

@login_required
def delete_account(request):
    if request.method == "POST":
        password = request.POST.get("password", "")

        if not request.user.check_password(password):
            messages.error(
                request,
                "Incorrect password. Your account has not been deactivated."
            )
            return redirect("delete_account")

        user = request.user
        user.is_active = False
        user.save(update_fields=["is_active"])

        logout(request)

        messages.success(
            request,
            "Your account has been deactivated. Please contact an administrator if you need access restored."
        )
        return redirect("login")

    return render(request, "accounts/delete_account.html")

# --------------------------------------------------
# CHANGE PASSWORD
# --------------------------------------------------

@login_required
def change_password(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)

        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was changed successfully.")
            return redirect("change_password")
    else:
        form = PasswordChangeForm(request.user)

    return render(request, "accounts/change_password.html", {
        "form": form,
    })


# --------------------------------------------------
# USER MANAGEMENT
# --------------------------------------------------

@superuser_required
def user_management(request):
    search = request.GET.get("q", "").strip()

    users = User.objects.all().order_by("-date_joined")

    if search:
        users = users.filter(
            username__icontains=search
        ) | users.filter(
            email__icontains=search
        ) | users.filter(
            first_name__icontains=search
        ) | users.filter(
            last_name__icontains=search
        )

    context = {
        "users": users,
        "search": search,
        "total_users": User.objects.count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "staff_users": User.objects.filter(is_staff=True).count(),
    }

    return render(
        request,
        "accounts/user_management.html",
        context,
    )




# --------------------------------------------------
# CREATE USER
# --------------------------------------------------

@superuser_required
def create_user(request):
    if request.method == "POST":
        form = UserManagementForm(request.POST)

        if form.is_valid():
            user = form.save()
            record_activity(
                request,
                action="user_created",
                description=f"Created user account '{user.username}'.",
                target_user=user,
            )

            messages.success(
                request,
                f"User '{user.username}' was created successfully."
            )

            return redirect("user_management")
    else:
        form = UserManagementForm()

    return render(
        request,
        "accounts/create_user.html",
        {"form": form},
    )




# --------------------------------------------------
# EDIT USER
# --------------------------------------------------

@superuser_required
def edit_user(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target_user)

        if form.is_valid():
            new_role = form.cleaned_data["role"]

            # Prevent removing the last active superuser.
            if (
                target_user.is_superuser
                and target_user.is_active
                and new_role != "admin"
                and User.objects.filter(
                    is_superuser=True,
                    is_active=True,
                ).count() <= 1
            ):
                form.add_error(
                    "role",
                    "You cannot remove the last active administrator."
                )
            else:
                form.save()
                record_activity(
                    request,
                    action="user_updated",
                    description=f"Updated user account '{target_user.username}'.",
                    target_user=target_user,
                )

                messages.success(
                    request,
                    f"User '{target_user.username}' updated successfully."
                )
                return redirect("user_management")

    else:
        form = UserEditForm(instance=target_user)

    return render(
        request,
        "accounts/edit_user.html",
        {
            "form": form,
            "target_user": target_user,
        },
    )




# --------------------------------------------------
# ACTIVATE / DEACTIVATE USER
# --------------------------------------------------

@superuser_required
@require_POST
def toggle_user_status(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    # Prevent administrators from deactivating themselves.
    if target_user.pk == request.user.pk:
        record_activity(
            request,
            action="user_deactivation_attempt",
            description=f"Attempted to deactivate own account '{target_user.username}'.",
            target_user=target_user,
        )
        messages.error(
            request,
            "You cannot deactivate your own account."
        )
        return redirect("user_management")

    # Deactivate an active account.
    if target_user.is_active:

        # Protect the last active administrator.
        if (
            target_user.is_superuser
            and User.objects.filter(
                is_superuser=True,
                is_active=True,
            ).count() <= 1
        ):
            messages.error(
                request,
                "You cannot deactivate the last active administrator."
            )
            return redirect("user_management")

        target_user.is_active = False
        target_user.save(update_fields=["is_active"])

        record_activity(
            request,
            action="user_deactivated",
            description=f"Deactivated user account '{target_user.username}'.",
            target_user=target_user,
        )

        messages.success(
            request,
            f"User '{target_user.username}' was deactivated."
        )

    else:
        target_user.is_active = True
        target_user.save(update_fields=["is_active"])

        record_activity(
            request,
            action="user_activated",
            description=f"Activated user account '{target_user.username}'.",
            target_user=target_user,
        )

        messages.success(
            request,
            f"User '{target_user.username}' was activated."
        )

    return redirect("user_management")




# --------------------------------------------------
# ADMIN PASSWORD RESET
# --------------------------------------------------

@superuser_required
def reset_user_password(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)

    if request.method == "POST":
        form = SetPasswordForm(target_user, request.POST)

        if form.is_valid():
            form.save()

            record_activity(
                request,
                action="password_reset",
                description=f"Reset password for user '{target_user.username}'.",
                target_user=target_user,
            )

            messages.success(
                request,
                f"Password for '{target_user.username}' was reset successfully."
            )

            return redirect("user_management")
    else:
        form = SetPasswordForm(target_user)

    return render(
        request,
        "accounts/reset_user_password.html",
        {
            "form": form,
            "target_user": target_user,
        },
    )



def record_activity(request, action, description, target_user=None):
    """Save an activity performed by the current authenticated user."""

    ip_address = request.META.get("REMOTE_ADDR")

    ActivityLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        target_user=target_user,
        action=action,
        description=description,
        ip_address=ip_address,
    )



# --------------------------------------------------
# ADMIN ACTIVITY LOG
# --------------------------------------------------



@superuser_required
def activity_log(request):
    search = request.GET.get("q", "").strip()
    selected_action = request.GET.get("action", "").strip()
    start_date_input = request.GET.get("start_date", "").strip()
    end_date_input = request.GET.get("end_date", "").strip()

    start_date = parse_date(start_date_input)
    end_date = parse_date(end_date_input)

    logs = ActivityLog.objects.select_related(
        "actor",
        "target_user",
    ).all()

    # Search
    if search:
        logs = logs.filter(
            Q(description__icontains=search)
            | Q(actor__username__icontains=search)
            | Q(target_user__username__icontains=search)
        )

    # Action filter
    valid_actions = dict(ActivityLog.ACTION_CHOICES)

    if selected_action in valid_actions:
        logs = logs.filter(action=selected_action)
    else:
        selected_action = ""

    # Date filters
    if start_date:
        logs = logs.filter(created_at__date__gte=start_date)

    if end_date:
        logs = logs.filter(created_at__date__lte=end_date)

    # Export data
    export_format = request.GET.get("export", "").lower()

    if export_format in ("csv", "xlsx"):
        filename_date = timezone.localdate().strftime("%Y%m%d")

        def safe_value(value):
            value = str(value or "")
            if value.startswith(("=", "+", "-", "@", "\t", "\r")):
                return "'" + value
            return value

        headers = [
            "Activity",
            "Description",
            "Performed By",
            "Affected User",
            "IP Address",
            "Date & Time",
        ]

        rows = []
        for log in logs.iterator():
            rows.append([
                safe_value(log.get_action_display()),
                safe_value(log.description),
                safe_value(log.actor.username if log.actor else "System / Unknown"),
                safe_value(log.target_user.username if log.target_user else ""),
                safe_value(log.ip_address or ""),
                timezone.localtime(log.created_at).strftime("%Y-%m-%d %I:%M:%S %p"),
            ])

        if export_format == "csv":
            response = HttpResponse(
                content_type="text/csv; charset=utf-8-sig"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="activity_log_{filename_date}.csv"'
            )

            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow(headers)
            writer.writerows(rows)

            return response

        # Excel export
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = "Activity Log"

        worksheet.append(headers)

        for row in rows:
            worksheet.append(row)

        # Header styling
        for cell in worksheet[1]:
            cell.font = Font(
                bold=True,
                color="FFFFFF",
                size=11,
            )
            cell.fill = PatternFill(
                fill_type="solid",
                fgColor="172554",
            )
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

        worksheet.row_dimensions[1].height = 25

        # Column widths
        column_widths = {
            "A": 22,
            "B": 55,
            "C": 22,
            "D": 22,
            "E": 20,
            "F": 25,
        }

        for column, width in column_widths.items():
            worksheet.column_dimensions[column].width = width

        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions

        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            f'attachment; filename="activity_log_{filename_date}.xlsx"'
        )

        workbook.save(response)
        return response

    # Pagination
    paginator = Paginator(logs, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "logs": page_obj,
        "page_obj": page_obj,
        "paginator": paginator,
        "search": search,
        "selected_action": selected_action,
        "action_choices": ActivityLog.ACTION_CHOICES,
        "start_date": start_date_input,
        "end_date": end_date_input,
        "total_logs": ActivityLog.objects.count(),
        "filtered_logs": paginator.count,
    }

    return render(
        request,
        "accounts/activity_log.html",
        context,
    )





@login_required
@require_POST
def save_theme(request):
    from django.utils.http import url_has_allowed_host_and_scheme

    theme = request.POST.get("theme", "system")
    valid_themes = {"light", "dark", "system"}

    if theme not in valid_themes:
        messages.error(request, "Invalid theme selection.")
    else:
        preference, created = UserPreference.objects.get_or_create(
            user=request.user,
            defaults={"theme": "system"},
        )

        preference.theme = theme
        preference.save(update_fields=["theme", "updated_at"])

        messages.success(request, "Appearance preference saved successfully.")

    previous_page = request.META.get("HTTP_REFERER")

    if previous_page and url_has_allowed_host_and_scheme(
        previous_page,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(previous_page)

    return redirect("pos_home")

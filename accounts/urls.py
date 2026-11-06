
from django.urls import path
from django.contrib.auth import views as auth_views

from . import views


urlpatterns = [
    # Registration
    path("user/register", views.register, name="register"),

    # Email verification
    path(
        "user/verify-email/<uidb64>/<token>/",
        views.verify_email,
        name="verify_email",
    ),

    path(
        "user/resend-verification/",
        views.resend_verification,
        name="resend_verification",
    ),

    # Forgot password
    path(
        "user/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/emails/password_reset_email.txt",
            subject_template_name="accounts/emails/password_reset_subject.txt",
            success_url="/user/password-reset/done/",
        ),
        name="password_reset",
    ),

    path(
        "user/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),

    # Reset password using email link
    path(
        "user/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/user/reset/complete/",
        ),
        name="password_reset_confirm",
    ),

    path(
        "user/reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),

    # Login and logout
    path("", views.login_user, name="login"),
    path("user/logout", views.logout_user, name="logout"),

    # Dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
]

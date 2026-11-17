
from django.conf import settings
from django.db import models


class ActivityLog(models.Model):

    ACTION_CHOICES = [
        ("user_created", "User Created"),
        ("user_updated", "User Updated"),
        ("user_activated", "User Activated"),
        ("user_deactivated", "User Deactivated"),
        ("password_reset", "Password Reset"),
        ("login", "Login"),
        ("logout", "Logout"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performed_activity_logs",
    )

    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_activity_logs",
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
    )

    description = models.TextField()

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        return f"{self.get_action_display()} - {self.created_at}"



class UserPreference(models.Model):

    THEME_CHOICES = [
        ("light", "Light"),
        ("dark", "Dark"),
        ("system", "System Default"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preference",
    )

    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default="system",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} Preferences"

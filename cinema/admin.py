from django.contrib import admin

from .models import Booking, CinemaHall, Movie, Show, Ticket
from .utils import generate_seats


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):

    list_display = ("title", "language", "duration", "is_active")

    list_filter = ("is_active", "language")

    search_fields = ("title",)


@admin.register(CinemaHall)
class CinemaHallAdmin(admin.ModelAdmin):

    list_display = ("name", "total_seats", "is_active")


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):

    list_display = (
        "movie",
        "hall",
        "show_date",
        "start_time",
        "ticket_price",
    )

    list_filter = ("show_date", "hall")

    def save_model(self, request, obj, form, change):

        is_new = obj.pk is None

        super().save_model(request, obj, form, change)

        if is_new:
            generate_seats(obj)


class TicketInline(admin.TabularInline):

    model = Ticket

    extra = 0

    can_delete = False

    readonly_fields = ("ticket_number", "seat", "price", "used", "used_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Sales records are read-only here: cancel them from the counter
    (Cinema > Bookings) so seats are released correctly."""

    list_display = (
        "booking_number",
        "show",
        "total",
        "payment_method",
        "status",
        "created_by",
        "created_at",
    )

    list_filter = ("status", "payment_method")

    search_fields = ("booking_number", "customer_name", "customer_phone")

    inlines = [TicketInline]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

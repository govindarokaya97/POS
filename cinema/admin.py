from django.contrib import admin

from .models import Booking, CinemaHall, Movie, Seat, Show, Ticket
from .utils import generate_seats


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):

    list_display = ("title", "language", "grade", "screen_format", "duration", "is_active")

    list_filter = ("is_active", "language")

    search_fields = ("title",)


@admin.register(CinemaHall)
class CinemaHallAdmin(admin.ModelAdmin):

    list_display = ("name", "total_seats", "gold_rows", "is_active")


@admin.register(Show)
class ShowAdmin(admin.ModelAdmin):

    list_display = (
        "movie",
        "hall",
        "show_date",
        "start_time",
        "gold_price",
        "silver_price",
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
        "vat",
        "local_tax",
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


@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    """Take seats out of sale (broken seat, owner's seat ...) or put them back."""

    list_display = ("seat_number", "show", "section", "is_booked", "is_blocked")

    list_filter = ("show", "section", "is_blocked", "is_booked")

    search_fields = ("seat_number",)

    actions = ["make_unavailable", "make_available"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Mark selected seats UNAVAILABLE (not sold)")
    def make_unavailable(self, request, queryset):
        updated = queryset.filter(is_booked=False).update(
            is_blocked=True, held_by=None, held_until=None
        )
        skipped = queryset.count() - updated
        self.message_user(
            request,
            f"{updated} seat(s) made unavailable."
            + (f" {skipped} already-sold seat(s) were left alone." if skipped else ""),
        )

    @admin.action(description="Mark selected seats AVAILABLE again")
    def make_available(self, request, queryset):
        updated = queryset.update(is_blocked=False)
        self.message_user(request, f"{updated} seat(s) made available.")

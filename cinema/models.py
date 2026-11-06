from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from .pricing import (
    DEFAULT_GOLD_PRICE,
    DEFAULT_SILVER_PRICE,
    GOLD,
    SECTION_CHOICES,
)


class Movie(models.Model):

    title = models.CharField(max_length=200)

    duration = models.PositiveIntegerField(help_text="Duration in minutes")

    language = models.CharField(max_length=50, default="Nepali")

    grade = models.CharField(
        max_length=10, blank=True, help_text="Rating printed on the invoice, e.g. PG"
    )

    screen_format = models.CharField(
        max_length=10, default="2D", help_text="e.g. 2D, 3D"
    )

    description = models.TextField(blank=True)

    poster = models.ImageField(upload_to="movies/", blank=True, null=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


class CinemaHall(models.Model):

    name = models.CharField(max_length=100)

    total_seats = models.PositiveIntegerField(default=100)

    gold_rows = models.PositiveIntegerField(
        default=3,
        help_text=(
            "Only used when the Seat layout below is empty: this many rows "
            "at the back (GA, GB, ...) are Gold, the rest Silver (A, B, ...)."
        ),
    )

    layout = models.TextField(
        blank=True,
        help_text=(
            "Optional exact seat map, one row per line, back row first: "
            "'GA gold ooooo..........ooooo'  (o = seat, . = empty space; "
            "a line with just 'gap' is a walkway). See cinema/layouts/audi1.txt."
        ),
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        from .utils import parse_layout

        try:
            parse_layout(self.layout)
        except ValueError as e:
            raise ValidationError({"layout": str(e)})

    def save(self, *args, **kwargs):
        from .utils import parse_layout

        if self.layout.strip():
            try:
                self.total_seats = sum(
                    row.get("pattern", "").count("o")
                    for row in parse_layout(self.layout)
                )
            except ValueError:
                pass
        super().save(*args, **kwargs)


class Show(models.Model):

    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="shows",
    )

    hall = models.ForeignKey(
        CinemaHall,
        on_delete=models.CASCADE,
        related_name="shows",
    )

    show_date = models.DateField()

    start_time = models.TimeField()

    gold_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=DEFAULT_GOLD_PRICE,
        help_text="Full price of a Gold seat, VAT and local tax included.",
    )

    silver_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=DEFAULT_SILVER_PRICE,
        help_text="Full price of a Silver seat, VAT and local tax included.",
    )

    # Single price from the first version. No longer used (see gold/silver).
    ticket_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-show_date", "start_time"]

    def __str__(self):
        return f"{self.movie} - {self.show_date} {self.start_time}"

    def price_for(self, section):
        return self.gold_price if section == GOLD else self.silver_price

    @property
    def starts_at(self):
        return timezone.make_aware(
            datetime.combine(self.show_date, self.start_time)
        )

    @property
    def ends_at(self):
        return self.starts_at + timedelta(minutes=self.movie.duration)

    @property
    def has_ended(self):
        """Counter stops selling once the movie is over."""
        return timezone.now() > self.ends_at


class Seat(models.Model):

    show = models.ForeignKey(
        Show,
        on_delete=models.CASCADE,
        related_name="seats",
    )

    seat_number = models.CharField(max_length=10)

    is_booked = models.BooleanField(default=False)

    section = models.CharField(
        max_length=10, choices=SECTION_CHOICES, default="silver"
    )

    # Unavailable: taken out of sale by staff (broken seat, reserved for
    # the owner ...). Set from Admin > Seats.
    is_blocked = models.BooleanField(default=False)

    # Reserved: a counter holds the seat while the cashier is at billing, so
    # two counters cannot pick the same seat at once. Expires on its own.
    held_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    held_until = models.DateTimeField(null=True, blank=True)

    # Position on the seat map: row 0 is the back row, col 0 the left edge.
    row_index = models.PositiveSmallIntegerField(default=0)

    col_index = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("show", "seat_number")]

    def __str__(self):
        return self.seat_number

    def state_for(self, user, now=None):
        """sold | unavailable | reserved | available - as seen by `user`.
        A seat the user holds themselves counts as available to them."""
        now = now or timezone.now()

        if self.is_booked:
            return "sold"
        if self.is_blocked:
            return "unavailable"
        if (
            self.held_until
            and self.held_until > now
            and self.held_by_id != getattr(user, "id", None)
        ):
            return "reserved"
        return "available"


class Booking(models.Model):
    """One invoice = one seat. (A counter sale of 3 seats makes 3 invoices.)"""

    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("card", "Card"),
        ("esewa", "eSewa"),
        ("khalti", "Khalti"),
    )

    STATUS_CHOICES = (
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
    )

    booking_number = models.CharField(max_length=30, unique=True)

    # Seats paid for together share a sale_ref; each seat is its own invoice.
    sale_ref = models.CharField(max_length=30, blank=True, db_index=True)

    show = models.ForeignKey(
        Show,
        on_delete=models.PROTECT,
        related_name="bookings",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="cinema_bookings",
    )

    customer_name = models.CharField(max_length=100, blank=True)

    customer_phone = models.CharField(max_length=20, blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    vat_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    vat = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    local_tax_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0
    )

    local_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    return_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cash",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="confirmed",
    )

    cancelled_at = models.DateTimeField(null=True, blank=True)

    cancelled_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cinema_cancellations",
    )

    # How many times the invoice page has been opened for printing. The
    # first print is the original; every later one is marked as a copy.
    print_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.booking_number

    @property
    def is_cancelled(self):
        return self.status == "cancelled"


class Ticket(models.Model):
    """One admission slip (one seat). The ticket_number is what gets scanned."""

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="tickets",
    )

    seat = models.ForeignKey(
        Seat,
        on_delete=models.PROTECT,
        related_name="tickets",
    )

    ticket_number = models.CharField(max_length=40, unique=True)

    # Short random code: this is what the QR holds and what is printed
    # under it (hard to guess, unlike the sequential invoice number).
    code = models.CharField(max_length=12, blank=True, db_index=True)

    section = models.CharField(
        max_length=10, choices=SECTION_CHOICES, default="silver"
    )

    price = models.DecimalField(max_digits=10, decimal_places=2)

    used = models.BooleanField(default=False)

    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.ticket_number

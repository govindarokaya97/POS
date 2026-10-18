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
            "How many rows, counted from the back of the hall, are Gold. "
            "All other rows are Silver. Applies to shows created afterwards."
        ),
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


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

    class Meta:
        unique_together = [("show", "seat_number")]

    def __str__(self):
        return self.seat_number


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

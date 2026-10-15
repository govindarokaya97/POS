import logging
import uuid
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import groupby

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.models import ShopSetting
from core.permissions import staff_required

from .models import Booking, Movie, Seat, Show, Ticket
from .utils import generate_seats, seat_row, seat_sort_key, ticket_barcode_svg

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class BookingError(Exception):
    """A problem the cashier can fix (shown as a message, not a crash)."""


def _default_vat():
    """Counter default VAT %. Set CINEMA_VAT_PERCENT in settings.py (e.g. 13)."""
    try:
        return Decimal(str(getattr(settings, "CINEMA_VAT_PERCENT", "0")))
    except InvalidOperation:
        return Decimal("0")


def _money(raw, label, default="0"):
    raw = (raw or "").strip() or default

    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise BookingError(f"{label} is not a valid number.")

    if not value.is_finite() or value < 0:
        raise BookingError(f"{label} cannot be negative.")

    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _calculate(price, seat_count, discount, vat_percent):
    subtotal = (price * seat_count).quantize(TWO_PLACES)

    if discount > subtotal:
        raise BookingError("Discount cannot exceed the subtotal.")

    taxable = subtotal - discount

    vat = (taxable * vat_percent / 100).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    return {
        "subtotal": subtotal,
        "discount": discount,
        "vat": vat,
        "total": (taxable + vat).quantize(TWO_PLACES),
    }


def _parse_seat_ids(values):
    ids = []

    for raw in values:
        try:
            seat_id = int(raw)
        except (TypeError, ValueError):
            raise BookingError("Invalid seat selection.")
        if seat_id not in ids:
            ids.append(seat_id)

    return ids


def _day_bounds(day):
    """[start, end) aware datetimes for a local calendar day.

    Used instead of created_at__date so it works on MySQL even when the
    server has no timezone tables loaded.
    """
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def _parse_day(raw, default):
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def _get_show(show_id):
    return get_object_or_404(
        Show.objects.select_related("movie", "hall"),
        id=show_id,
    )


def _ensure_seats(show):
    if not show.seats.exists():
        generate_seats(show)


# --------------------------------------------------------------------------
# Counter dashboard
# --------------------------------------------------------------------------

@staff_required
def cinema_dashboard(request):

    today = timezone.localdate()

    upcoming = Show.objects.filter(
        show_date__gte=today
    ).select_related("hall").order_by("show_date", "start_time")

    movies = Movie.objects.filter(is_active=True).prefetch_related(
        Prefetch("shows", queryset=upcoming, to_attr="upcoming_shows")
    )

    shows = Show.objects.filter(
        show_date__gte=today
    ).select_related(
        "movie", "hall"
    ).annotate(
        seat_count=Count("seats"),
        sold_count=Count("seats", filter=Q(seats__is_booked=True)),
    ).order_by("show_date", "start_time")

    today_shows = [s for s in shows if s.show_date == today]
    later_shows = [s for s in shows if s.show_date > today][:10]

    start, end = _day_bounds(today)

    confirmed_today = Booking.objects.filter(
        status="confirmed",
        created_at__gte=start,
        created_at__lt=end,
    )

    context = {
        "movies": movies,
        "today_shows": today_shows,
        "later_shows": later_shows,
        "today": today,
        "tickets_sold_today": Ticket.objects.filter(
            booking__in=confirmed_today
        ).count(),
        "revenue_today": confirmed_today.aggregate(
            t=Sum("total")
        )["t"] or Decimal("0.00"),
        "bookings_today": confirmed_today.count(),
    }

    return render(request, "cinema/dashboard.html", context)


# --------------------------------------------------------------------------
# Step 1: pick seats
# --------------------------------------------------------------------------

@staff_required
def seat_selection(request, id):

    show = _get_show(id)

    if show.has_ended:
        messages.error(request, "This show has already ended.")
        return redirect("cinema_dashboard")

    _ensure_seats(show)

    seats = sorted(show.seats.all(), key=seat_sort_key)

    rows = [
        (label, list(group))
        for label, group in groupby(seats, key=seat_row)
    ]

    context = {
        "show": show,
        "rows": rows,
        "sold": sum(1 for s in seats if s.is_booked),
        "total_seats": len(seats),
    }

    return render(request, "cinema/seats.html", context)


# --------------------------------------------------------------------------
# Step 2: bill + payment
# --------------------------------------------------------------------------

def _create_booking(request, show):
    """Runs inside transaction.atomic(). Locks the seats so two counters
    can never sell the same seat."""

    seat_ids = _parse_seat_ids(request.POST.getlist("seats"))

    if not seat_ids:
        raise BookingError("Select at least one seat.")

    seats = list(
        Seat.objects.select_for_update().filter(show=show, id__in=seat_ids)
    )

    if len(seats) != len(seat_ids):
        raise BookingError("Some of the selected seats are not valid.")

    taken = [s.seat_number for s in seats if s.is_booked]

    if taken:
        raise BookingError(
            "Already sold: " + ", ".join(sorted(taken, key=seat_sort_key))
        )

    discount = _money(request.POST.get("discount"), "Discount")

    vat_percent = _money(
        request.POST.get("vat_percent"),
        "VAT",
        default=str(_default_vat()),
    )

    if vat_percent > 100:
        raise BookingError("VAT cannot be more than 100%.")

    payment_method = request.POST.get("payment_method", "cash")

    if payment_method not in dict(Booking.PAYMENT_METHODS):
        raise BookingError("Invalid payment method.")

    amounts = _calculate(show.ticket_price, len(seats), discount, vat_percent)

    total = amounts["total"]

    # Blank "received" means the exact amount was paid.
    received = _money(
        request.POST.get("paid_amount"),
        "Received amount",
        default=str(total),
    )

    if received < total:
        raise BookingError(
            "Received amount is less than the total. "
            "Tickets must be paid in full."
        )

    seats.sort(key=seat_sort_key)

    booking = Booking.objects.create(
        booking_number=f"TEMP-{uuid.uuid4().hex[:12]}",
        show=show,
        created_by=request.user,
        customer_name=request.POST.get("customer_name", "").strip()[:100],
        customer_phone=request.POST.get("customer_phone", "").strip()[:20],
        subtotal=amounts["subtotal"],
        discount=amounts["discount"],
        vat_percent=vat_percent,
        vat=amounts["vat"],
        total=total,
        paid_amount=total,
        return_amount=(received - total).quantize(TWO_PLACES),
        payment_method=payment_method,
    )

    booking.booking_number = f"BK-{booking.pk:05d}"
    booking.save(update_fields=["booking_number"])

    Ticket.objects.bulk_create([
        Ticket(
            booking=booking,
            seat=seat,
            ticket_number=f"{booking.booking_number}-{seat.seat_number}",
            price=show.ticket_price,
        )
        for seat in seats
    ])

    Seat.objects.filter(id__in=seat_ids).update(is_booked=True)

    return booking


def _load_selected_seats(show, seat_ids):
    seats = list(Seat.objects.filter(show=show, id__in=seat_ids))

    if not seats or len(seats) != len(seat_ids):
        raise BookingError("Select at least one valid seat.")

    taken = [s.seat_number for s in seats if s.is_booked]

    if taken:
        raise BookingError(
            "Already sold: " + ", ".join(sorted(taken, key=seat_sort_key))
        )

    return sorted(seats, key=seat_sort_key)


@staff_required
def ticket_checkout(request, id):

    show = _get_show(id)

    if show.has_ended:
        messages.error(request, "This show has already ended.")
        return redirect("cinema_dashboard")

    source = request.POST if request.method == "POST" else request.GET

    try:
        seat_ids = _parse_seat_ids(source.getlist("seats"))
        seats = _load_selected_seats(show, seat_ids)
    except BookingError as e:
        messages.error(request, str(e))
        return redirect("seat_selection", id=show.id)

    if request.method == "POST":

        try:
            with transaction.atomic():
                booking = _create_booking(request, show)

        except BookingError as e:
            messages.error(request, str(e))

        except Exception:
            logger.exception("Cinema booking failed")
            messages.error(
                request,
                "Could not create the booking. Nothing was charged.",
            )
            return redirect("seat_selection", id=show.id)

        else:
            messages.success(
                request,
                f"Booking {booking.booking_number} created.",
            )
            return redirect(
                f"{reverse('ticket_print', kwargs={'id': booking.id})}"
                "?print=true"
            )

    subtotal = (show.ticket_price * len(seats)).quantize(TWO_PLACES)

    context = {
        "show": show,
        "seats": seats,
        "seat_count": len(seats),
        "subtotal": subtotal,
        "default_vat": _default_vat(),
        "payment_methods": Booking.PAYMENT_METHODS,
        # Keep what the cashier typed if the form comes back with an error.
        "form": request.POST if request.method == "POST" else {},
    }

    return render(request, "cinema/ticket_checkout.html", context)


# --------------------------------------------------------------------------
# Bill + ticket print
# --------------------------------------------------------------------------

@staff_required
def ticket_print(request, id):

    booking = get_object_or_404(
        Booking.objects.select_related(
            "show__movie", "show__hall", "created_by"
        ),
        id=id,
    )

    tickets = list(booking.tickets.select_related("seat"))

    for ticket in tickets:
        ticket.barcode_svg = ticket_barcode_svg(ticket.ticket_number)

    context = {
        "booking": booking,
        "show": booking.show,
        "tickets": tickets,
        "shop": ShopSetting.objects.first(),
        "payment_label": booking.get_payment_method_display(),
        "received": booking.paid_amount + booking.return_amount,
        "auto_print": (
            request.GET.get("print") == "true" and not booking.is_cancelled
        ),
    }

    return render(request, "cinema/ticket_print.html", context)


# --------------------------------------------------------------------------
# Bookings list + cancel
# --------------------------------------------------------------------------

@staff_required
def booking_list(request):

    today = timezone.localdate()

    day = _parse_day(request.GET.get("date"), today)
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")

    start, end = _day_bounds(day)

    bookings = Booking.objects.select_related(
        "show__movie", "show__hall", "created_by"
    ).annotate(
        ticket_count=Count("tickets")
    ).order_by("-created_at", "-id")   # annotate() drops Meta.ordering

    if query:
        bookings = bookings.filter(
            Q(booking_number__icontains=query)
            | Q(customer_name__icontains=query)
            | Q(customer_phone__icontains=query)
            | Q(id__in=Ticket.objects.filter(
                ticket_number__icontains=query
            ).values("booking_id"))
        )
    else:
        # Searching looks across all days; browsing is one day at a time.
        bookings = bookings.filter(created_at__gte=start, created_at__lt=end)

    if status in dict(Booking.STATUS_CHOICES):
        bookings = bookings.filter(status=status)

    page = Paginator(bookings, 25).get_page(request.GET.get("page"))

    params = request.GET.copy()
    params.pop("page", None)

    context = {
        "page": page,
        "day": day,
        "query": query,
        "status": status,
        "querystring": params.urlencode(),
    }

    return render(request, "cinema/booking_list.html", context)


@staff_required
@require_POST
def booking_cancel(request, id):

    try:
        with transaction.atomic():

            booking = get_object_or_404(
                Booking.objects.select_for_update(), id=id
            )

            if booking.is_cancelled:
                raise BookingError("This booking is already cancelled.")

            if booking.tickets.filter(used=True).exists():
                raise BookingError(
                    "Cannot cancel: a ticket from this booking has "
                    "already been used for entry."
                )

            if booking.show.has_ended:
                raise BookingError("Cannot cancel: the show has ended.")

            Seat.objects.filter(
                id__in=booking.tickets.values_list("seat_id", flat=True)
            ).update(is_booked=False)

            booking.status = "cancelled"
            booking.cancelled_at = timezone.now()
            booking.cancelled_by = request.user
            booking.save(
                update_fields=["status", "cancelled_at", "cancelled_by"]
            )

    except BookingError as e:
        messages.error(request, str(e))

    else:
        messages.success(
            request,
            f"{booking.booking_number} cancelled. Seats released. "
            f"Refund Rs {booking.total}.",
        )

    return redirect("booking_list")


# --------------------------------------------------------------------------
# Entry gate
# --------------------------------------------------------------------------

def _verify(code):

    with transaction.atomic():

        ticket = Ticket.objects.select_for_update().filter(
            ticket_number__iexact=code
        ).first()

        if not ticket:
            return {"status": "invalid", "message": "Ticket not found."}

        booking = ticket.booking
        show = booking.show

        details = {
            "movie": show.movie.title,
            "hall": show.hall.name,
            "seat": ticket.seat.seat_number,
            "date": show.show_date.strftime("%d %b %Y"),
            "time": show.start_time.strftime("%H:%M"),
            "ticket": ticket.ticket_number,
        }

        if booking.is_cancelled:
            return {"status": "cancelled",
                    "message": "This booking was cancelled.", **details}

        if ticket.used:
            when = timezone.localtime(ticket.used_at).strftime("%H:%M")
            return {"status": "already_used",
                    "message": f"Already used at {when}.", **details}

        if show.show_date != timezone.localdate():
            return {"status": "wrong_date",
                    "message": "This ticket is for a different date.",
                    **details}

        if show.has_ended:
            return {"status": "expired",
                    "message": "This show has ended.", **details}

        ticket.used = True
        ticket.used_at = timezone.now()
        ticket.save(update_fields=["used", "used_at"])

        return {"status": "valid", "message": "Entry allowed.", **details}


@staff_required
def verify_ticket(request):

    if request.method == "POST":
        code = request.POST.get("ticket", "").strip()

        if not code:
            return JsonResponse(
                {"status": "invalid", "message": "Scan or type a ticket number."}
            )

        return JsonResponse(_verify(code))

    return render(request, "cinema/verify.html")


# --------------------------------------------------------------------------
# Daily collection report
# --------------------------------------------------------------------------

@staff_required
def cinema_report(request):

    today = timezone.localdate()

    start_day = _parse_day(request.GET.get("from"), today)
    end_day = _parse_day(request.GET.get("to"), start_day)

    if end_day < start_day:
        start_day, end_day = end_day, start_day

    start, _ = _day_bounds(start_day)
    _, end = _day_bounds(end_day)

    in_range = Booking.objects.filter(created_at__gte=start, created_at__lt=end)

    confirmed = in_range.filter(status="confirmed")
    cancelled = in_range.filter(status="cancelled")

    totals = confirmed.aggregate(
        bookings=Count("id"),
        subtotal=Sum("subtotal"),
        discount=Sum("discount"),
        vat=Sum("vat"),
        total=Sum("total"),
    )

    cancelled_totals = cancelled.aggregate(
        bookings=Count("id"), total=Sum("total")
    )

    by_method = confirmed.values("payment_method").annotate(
        bookings=Count("id"), total=Sum("total")
    ).order_by("-total")

    method_names = dict(Booking.PAYMENT_METHODS)

    for row in by_method:
        row["label"] = method_names.get(
            row["payment_method"], row["payment_method"]
        )

    by_movie = confirmed.values("show__movie__title").annotate(
        tickets=Count("tickets"), total=Sum("total")
    ).order_by("-total")

    by_cashier = confirmed.values("created_by__username").annotate(
        bookings=Count("id"), total=Sum("total")
    ).order_by("-total")

    context = {
        "start_day": start_day,
        "end_day": end_day,
        "totals": totals,
        "tickets_sold": Ticket.objects.filter(booking__in=confirmed).count(),
        "cancelled_totals": cancelled_totals,
        "by_method": by_method,
        "by_movie": by_movie,
        "by_cashier": by_cashier,
    }

    return render(request, "cinema/report.html", context)

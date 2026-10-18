import logging
import uuid
from datetime import datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from itertools import groupby

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
from .pricing import (
    SECTION_CHOICES,
    local_tax_percent,
    prices_include_tax,
    tax_breakdown,
    vat_percent,
)
from .utils import generate_seats, seat_row, seat_sort_key, ticket_barcode_svg

logger = logging.getLogger(__name__)

TWO_PLACES = Decimal("0.01")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class BookingError(Exception):
    """A problem the cashier can fix (shown as a message, not a crash)."""


def _money(raw, label, default="0"):
    raw = (raw or "").strip() or default

    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise BookingError(f"{label} is not a valid number.")

    if not value.is_finite() or value < 0:
        raise BookingError(f"{label} cannot be negative.")

    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _price_lines(show, seats):
    """One line per seat: its section price split into base / VAT / local tax,
    plus the grand totals for the whole counter sale."""
    lines = []

    for seat in seats:
        price = show.price_for(seat.section)
        lines.append({
            "seat": seat,
            "section": seat.section,
            "section_label": seat.get_section_display(),
            "price": price,
            **tax_breakdown(price),
        })

    totals = {
        key: sum((line[key] for line in lines), Decimal("0.00"))
        for key in ("base", "vat", "local_tax", "total")
    }

    return lines, totals


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

    rows = []
    previous_section = None

    for label, group in groupby(seats, key=seat_row):
        row_seats = list(group)
        section = row_seats[0].section
        rows.append({
            "label": label,
            "seats": row_seats,
            "section": section,
            "section_label": row_seats[0].get_section_display(),
            "price": show.price_for(section),
            "starts_section": section != previous_section,
        })
        previous_section = section

    context = {
        "show": show,
        "rows": rows,
        "sold": sum(1 for s in seats if s.is_booked),
        "total_seats": len(seats),
        "vat_percent": vat_percent(),
        "local_tax_percent": local_tax_percent(),
        "tax_included": prices_include_tax(),
    }

    return render(request, "cinema/seats.html", context)


# --------------------------------------------------------------------------
# Step 2: bill + payment
# --------------------------------------------------------------------------

def _create_sale(request, show):
    """Runs inside transaction.atomic(). Locks the seats so two counters
    can never sell the same seat, then makes ONE INVOICE PER SEAT.

    Returns (bookings, change_to_return).
    """

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

    payment_method = request.POST.get("payment_method", "cash")

    if payment_method not in dict(Booking.PAYMENT_METHODS):
        raise BookingError("Invalid payment method.")

    seats.sort(key=seat_sort_key)

    lines, totals = _price_lines(show, seats)

    # Blank "received" means the exact amount was paid.
    received = _money(
        request.POST.get("paid_amount"),
        "Received amount",
        default=str(totals["total"]),
    )

    if received < totals["total"]:
        raise BookingError(
            "Received amount is less than the total. "
            "Tickets must be paid in full."
        )

    sale_ref = f"SL-{uuid.uuid4().hex[:10].upper()}"
    customer_name = request.POST.get("customer_name", "").strip()[:100]
    customer_phone = request.POST.get("customer_phone", "").strip()[:20]

    bookings = []

    for line in lines:
        seat = line["seat"]

        booking = Booking.objects.create(
            booking_number=f"TEMP-{uuid.uuid4().hex[:12]}",
            sale_ref=sale_ref,
            show=show,
            created_by=request.user,
            customer_name=customer_name,
            customer_phone=customer_phone,
            subtotal=line["base"],
            discount=Decimal("0.00"),
            vat_percent=line["vat_percent"],
            vat=line["vat"],
            local_tax_percent=line["local_tax_percent"],
            local_tax=line["local_tax"],
            total=line["total"],
            paid_amount=line["total"],
            return_amount=Decimal("0.00"),
            payment_method=payment_method,
        )

        booking.booking_number = f"BK-{booking.pk:05d}"
        booking.save(update_fields=["booking_number"])

        Ticket.objects.create(
            booking=booking,
            seat=seat,
            section=seat.section,
            ticket_number=f"{booking.booking_number}-{seat.seat_number}",
            price=line["total"],
        )

        bookings.append(booking)

    Seat.objects.filter(id__in=seat_ids).update(is_booked=True)

    return bookings, (received - totals["total"]).quantize(TWO_PLACES)


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
                bookings, change = _create_sale(request, show)

        except BookingError as e:
            messages.error(request, str(e))

        except Exception:
            logger.exception("Cinema booking failed")
            messages.error(
                request,
                "Could not create the invoices. Nothing was charged.",
            )
            return redirect("seat_selection", id=show.id)

        else:
            note = f"{len(bookings)} invoice(s) created."
            if change > 0:
                note += f" Return change: Rs {change}."
            messages.success(request, note)

            return redirect(
                f"{reverse('sale_print', kwargs={'ref': bookings[0].sale_ref})}"
                "?print=true"
            )

    lines, totals = _price_lines(show, seats)

    context = {
        "show": show,
        "lines": lines,
        "totals": totals,
        "seat_count": len(seats),
        "vat_percent": vat_percent(),
        "local_tax_percent": local_tax_percent(),
        "tax_included": prices_include_tax(),
        "payment_methods": Booking.PAYMENT_METHODS,
        # Keep what the cashier typed if the form comes back with an error.
        "form": request.POST if request.method == "POST" else {},
    }

    return render(request, "cinema/ticket_checkout.html", context)


# --------------------------------------------------------------------------
# Bill + ticket print
# --------------------------------------------------------------------------

def _render_invoices(request, bookings, *, single):
    """One printed slip per seat: the invoice and the entry ticket in one."""

    slips = []

    for booking in bookings:
        for ticket in booking.tickets.all():
            ticket.barcode_svg = ticket_barcode_svg(ticket.ticket_number)
            slips.append({"booking": booking, "ticket": ticket})

    context = {
        "slips": slips,
        "bookings": bookings,
        "show": bookings[0].show,
        "single": single,
        "booking": bookings[0],
        "shop": ShopSetting.objects.first(),
        "auto_print": (
            request.GET.get("print") == "true"
            and any(not b.is_cancelled for b in bookings)
        ),
    }

    return render(request, "cinema/ticket_print.html", context)


def _invoice_queryset():
    return Booking.objects.select_related(
        "show__movie", "show__hall", "created_by"
    ).prefetch_related("tickets__seat")


@staff_required
def ticket_print(request, id):
    """Reprint a single invoice (one seat)."""
    booking = get_object_or_404(_invoice_queryset(), id=id)
    return _render_invoices(request, [booking], single=True)


@staff_required
def sale_print(request, ref):
    """Print every invoice of one counter sale, one slip per seat."""
    bookings = list(_invoice_queryset().filter(sale_ref=ref).order_by("id"))

    if not bookings:
        messages.error(request, "Sale not found.")
        return redirect("cinema_dashboard")

    return _render_invoices(request, bookings, single=False)


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
    ).prefetch_related(
        "tickets__seat"
    ).order_by("-created_at", "-id")

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
            "section": ticket.get_section_display(),
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
        vat=Sum("vat"),
        local_tax=Sum("local_tax"),
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

    section_names = dict(SECTION_CHOICES)

    by_section = Ticket.objects.filter(
        booking__in=confirmed
    ).values("section").annotate(
        tickets=Count("id"), total=Sum("price")
    ).order_by("section")

    for row in by_section:
        row["label"] = section_names.get(row["section"], row["section"])

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
        "by_section": by_section,
        "by_movie": by_movie,
        "by_cashier": by_cashier,
    }

    return render(request, "cinema/report.html", context)

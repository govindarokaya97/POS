import re
from io import BytesIO

from django.utils.safestring import mark_safe

from .models import Seat

SEATS_PER_ROW = 10


def row_label(index):
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


def generate_seats(show):
    """Create the seat map for a show from its hall's seat count.

    Seats are laid out SEATS_PER_ROW to a row (A1..A10, B1..B10 ...). The
    last row is shorter if the hall size is not a multiple of SEATS_PER_ROW.
    Safe to call twice: existing seats are left alone.
    """
    total = show.hall.total_seats

    seats = []
    for n in range(total):
        row, col = divmod(n, SEATS_PER_ROW)
        seats.append(
            Seat(show=show, seat_number=f"{row_label(row)}{col + 1}")
        )

    Seat.objects.bulk_create(seats, ignore_conflicts=True)


_SEAT_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def seat_sort_key(seat):
    """A2 sorts before A10 (plain string sorting would not)."""
    number = getattr(seat, "seat_number", seat)
    match = _SEAT_RE.match(number)
    if not match:
        return (number, 0)
    return (match.group(1).upper().rjust(3), int(match.group(2)))


def seat_row(seat):
    match = _SEAT_RE.match(seat.seat_number)
    return match.group(1).upper() if match else ""


def ticket_barcode_svg(value):
    """Code128 barcode for a ticket number as inline SVG (scannable at the
    gate with the same kind of USB scanner used for product barcodes)."""
    try:
        import barcode
        from barcode.writer import SVGWriter

        buffer = BytesIO()
        barcode.get("code128", value, writer=SVGWriter()).write(
            buffer,
            options={
                "module_width": 0.25,
                "module_height": 8,
                "quiet_zone": 1,
                "write_text": False,
            },
        )
        svg = buffer.getvalue().decode("utf-8")
        return mark_safe(svg[svg.index("<svg"):])
    except Exception:
        # Never block a sale because the barcode could not be drawn.
        return ""

import re
from io import BytesIO

from django.utils.safestring import mark_safe

from .models import Seat
from .pricing import GOLD, SILVER

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
    """Create the seat map for a show from its hall.

    Seats are laid out SEATS_PER_ROW to a row (A1..A10, B1..B10 ...), row A
    being nearest the screen. The last `hall.gold_rows` rows (the back) are
    Gold, every row in front of them is Silver. Safe to call twice.
    """
    total = show.hall.total_seats
    row_count = -(-total // SEATS_PER_ROW)          # ceil
    first_gold_row = row_count - min(show.hall.gold_rows, row_count)

    seats = []
    for n in range(total):
        row, col = divmod(n, SEATS_PER_ROW)
        seats.append(
            Seat(
                show=show,
                seat_number=f"{row_label(row)}{col + 1}",
                section=GOLD if row >= first_gold_row else SILVER,
            )
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

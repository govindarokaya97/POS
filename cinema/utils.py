import re
import secrets
from decimal import ROUND_HALF_UP, Decimal

import segno
from django.utils.safestring import mark_safe

from .models import Seat, Ticket
from .pricing import GOLD, SILVER

SEATS_PER_ROW = 10          # only for halls with no seat layout

# No 0/O/1/I so a code read off a slip is never ambiguous.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def row_label(index):
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    label = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        label = chr(65 + rem) + label
    return label


# --------------------------------------------------------------------------
# Seat layout
# --------------------------------------------------------------------------

def parse_layout(text):
    """Parse a hall's seat layout.

    One row per line, back row first (the screen is at the bottom):

        GA gold   ooooo..........ooooo
        gap
        A  silver oooooooo...ooooooooo

    'o' is a seat, '.' an empty space (aisle); 'gap' is a blank walkway row.
    Blank lines and anything after '#' are ignored. Seats in a row are
    numbered left to right (A1, A2 ...). Raises ValueError with the line.
    """
    rows = []
    labels = set()

    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()

        if not line:
            continue

        if line.lower() == "gap":
            rows.append({"gap": True})
            continue

        parts = line.split()

        if len(parts) != 3:
            raise ValueError(
                f"Line {number}: expected 'ROW section pattern' "
                f"(e.g. 'A silver oooo..oooo'), got '{line}'."
            )

        label, section, pattern = parts
        label = label.upper()
        section = section.lower()

        if not re.fullmatch(r"[A-Z]{1,3}", label):
            raise ValueError(f"Line {number}: row name '{label}' must be 1-3 letters.")

        if label in labels:
            raise ValueError(f"Line {number}: row '{label}' is used twice.")

        if section not in (GOLD, SILVER):
            raise ValueError(f"Line {number}: section must be 'gold' or 'silver'.")

        if not re.fullmatch(r"[o.]+", pattern):
            raise ValueError(
                f"Line {number}: pattern may only contain 'o' (seat) and '.' (space)."
            )

        if "o" not in pattern:
            raise ValueError(f"Line {number}: row '{label}' has no seats.")

        labels.add(label)
        rows.append(
            {"gap": False, "label": label, "section": section, "pattern": pattern}
        )

    return rows



def _default_rows(hall):
    """Generate Gold rows first (GA, GB, GC...) followed by Silver rows (A, B, C...)."""
    total = hall.total_seats
    row_count = -(-total // SEATS_PER_ROW)
    gold_count = min(hall.gold_rows, row_count)

    rows = []
    remaining = total

    # Gold rows: GA, GB, GC... (top to bottom)
    for i in range(gold_count):
        seats = min(SEATS_PER_ROW, remaining)
        remaining -= seats

        rows.append({
            "gap": False,
            "label": "G" + row_label(i),
            "section": GOLD,
            "pattern": "o" * seats,
        })

    # Silver rows: A, B, C... (after Gold rows)
    for i in range(row_count - gold_count):
        seats = min(SEATS_PER_ROW, remaining)
        remaining -= seats

        rows.append({
            "gap": False,
            "label": row_label(i),
            "section": SILVER,
            "pattern": "o" * seats,
        })

    return rows


    


def generate_seats(show):
    """Create or repair seat labels, sections and positions for a show."""
    hall = show.hall
    rows = parse_layout(hall.layout) if hall.layout.strip() else _default_rows(hall)

    existing = {
        seat.seat_number: seat
        for seat in Seat.objects.filter(show=show)
    }

    to_create = []
    to_update = []

    for row_index, row in enumerate(rows):
        if row.get("gap"):
            continue

        number = 0

        for col_index, char in enumerate(row["pattern"]):
            if char != "o":
                continue

            number += 1
            seat_number = f'{row["label"]}{number}'

            seat = existing.get(seat_number)

            if seat is None:
                to_create.append(
                    Seat(
                        show=show,
                        seat_number=seat_number,
                        section=row["section"],
                        row_index=row_index,
                        col_index=col_index,
                    )
                )
            else:
                changed = False

                if seat.section != row["section"]:
                    seat.section = row["section"]
                    changed = True

                if seat.row_index != row_index:
                    seat.row_index = row_index
                    changed = True

                if seat.col_index != col_index:
                    seat.col_index = col_index
                    changed = True

                if changed:
                    to_update.append(seat)

    if to_create:
        Seat.objects.bulk_create(to_create, ignore_conflicts=True)

    if to_update:
        Seat.objects.bulk_update(
            to_update,
            ["section", "row_index", "col_index"],
        )



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


# --------------------------------------------------------------------------
# Ticket code, QR code, amount in words
# --------------------------------------------------------------------------

def new_ticket_code():
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
        if not Ticket.objects.filter(code=code).exists():
            return code


def ticket_code_svg(value):
    """Standard QR code for the ticket as inline SVG.

    make_qr (not make) so segno never picks a Micro QR code, which many
    scanners and phone cameras cannot read.
    """
    return mark_safe(
        segno.make_qr(value, error="m").svg_inline(scale=4, border=1, omitsize=True)
    )


def amount_in_words(amount):
    """300 -> 'Three Hundred Rupees Only' (same wording as the invoice)."""
    from billing.utils import _whole_number_words

    cents = int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    rupees, paisa = divmod(cents, 100)

    text = f"{_whole_number_words(rupees)} Rupees"
    if paisa:
        text += f" and {_whole_number_words(paisa)} Paisa"
    return text + " Only"

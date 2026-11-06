
from cinema.models import Show, Seat, Ticket

expected = set()

for prefix, count in [
    ("GA", 10),
    ("GB", 8),
    ("GC", 10),
    ("GD", 17),
    ("GE", 19),
    ("A", 17),
    ("B", 15),
    ("C", 15),
    ("D", 15),
    ("E", 15),
    ("F", 15),
    ("G", 18),
    ("H", 18),
    ("I", 18),
    ("J", 18),
    ("K", 18),
    ("L", 12),
]:
    expected.update(
        f"{prefix}{i}" for i in range(1, count + 1)
    )

for show in Show.objects.all().order_by("id"):
    extras = Seat.objects.filter(show=show).exclude(
        seat_number__in=expected
    )

    print(f"\n--- SHOW {show.id}: {extras.count()} extra seats ---")

    for seat in extras.order_by("seat_number"):
        ticket_count = Ticket.objects.filter(seat=seat).count()

        print(
            f"{seat.seat_number} | "
            f"section={seat.section} | "
            f"booked={seat.is_booked} | "
            f"tickets={ticket_count} | "
            f"held_by={seat.held_by_id} | "
            f"held_until={seat.held_until}"
        )

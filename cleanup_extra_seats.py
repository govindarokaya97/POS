
from django.db import transaction
from django.utils import timezone

from cinema.models import Show, Seat, Ticket

EXPECTED_COUNTS = {
    "GA": 10,
    "GB": 8,
    "GC": 10,
    "GD": 17,
    "GE": 19,
    "A": 17,
    "B": 15,
    "C": 15,
    "D": 15,
    "E": 15,
    "F": 15,
    "G": 18,
    "H": 18,
    "I": 18,
    "J": 18,
    "K": 18,
    "L": 12,
}

expected = {
    f"{prefix}{number}"
    for prefix, count in EXPECTED_COUNTS.items()
    for number in range(1, count + 1)
}

deleted_total = 0
preserved_total = 0

with transaction.atomic():
    for show in Show.objects.all().order_by("id"):
        extras = Seat.objects.filter(show=show).exclude(
            seat_number__in=expected
        )

        deleted = 0
        preserved = 0

        for seat in extras:
            has_tickets = Ticket.objects.filter(seat=seat).exists()
            has_active_hold = (
                seat.held_until is not None
                and seat.held_until > timezone.now()
            )

            if (
                has_tickets
                or seat.is_booked
                or has_active_hold
                or seat.held_by_id is not None
            ):
                preserved += 1
                print(
                    f"PRESERVED Show {show.id}: {seat.seat_number} "
                    f"(booked={seat.is_booked}, "
                    f"tickets={Ticket.objects.filter(seat=seat).count()}, "
                    f"held_by={seat.held_by_id}, "
                    f"held_until={seat.held_until})"
                )
                continue

            seat.delete()
            deleted += 1

        deleted_total += deleted
        preserved_total += preserved

        remaining = Seat.objects.filter(show=show).count()

        print(
            f"Show {show.id}: removed={deleted}, "
            f"preserved_extra={preserved}, remaining={remaining}"
        )

print("\nCleanup finished.")
print("Total removed:", deleted_total)
print("Extra seats preserved for safety:", preserved_total)

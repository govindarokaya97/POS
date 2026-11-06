
from decimal import Decimal

from django.db import transaction

from cinema.models import CinemaHall, Show, Seat
from cinema.utils import generate_seats, parse_layout


layout = """
GE gold ooooooooo.........oooooooooo
gap
GD gold ooooooooo.........oooooooo
gap
GC gold ooooo.........ooooo
gap
GB gold oooo.........oooo
gap
GA gold ooooo.........ooooo
gap
L silver oooooo.........oooooo
gap
K silver ooooooooo.........ooooooooo
gap
J silver ooooooooo.........ooooooooo
gap
I silver ooooooooo.........ooooooooo
gap
H silver ooooooooo.........ooooooooo
gap
G silver ooooooooo.........ooooooooo
gap
F silver ooooooo.........oooooooo
gap
E silver ooooooo.........oooooooo
gap
D silver ooooooo.........oooooooo
gap
C silver ooooooo.........oooooooo
gap
B silver ooooooo.........oooooooo
gap
A silver ooooooooo.........oooooooo
""".strip()


# Validate counts before touching the database.
rows = parse_layout(layout)
gold_count = sum(
    row["pattern"].count("o")
    for row in rows
    if not row.get("gap") and row["section"] == "gold"
)
silver_count = sum(
    row["pattern"].count("o")
    for row in rows
    if not row.get("gap") and row["section"] == "silver"
)

print("Planned Gold seats:", gold_count)
print("Planned Silver seats:", silver_count)
print("Planned total:", gold_count + silver_count)

if (gold_count, silver_count) != (64, 194):
    raise ValueError(
        "Layout count is incorrect. Database was not changed."
    )


halls = CinemaHall.objects.filter(name="ABC HAll")
if not halls:
    raise ValueError("No cinema hall named ABC HAll was found.")

with transaction.atomic():
    for hall in halls:
        hall.layout = layout
        hall.total_seats = 258
        hall.save()

        for show in Show.objects.filter(hall=hall):
            generate_seats(show)

            show.gold_price = Decimal("400.00")
            show.silver_price = Decimal("300.00")
            show.save(update_fields=["gold_price", "silver_price"])

            seats = Seat.objects.filter(show=show)

            print(
                f"Show {show.id}: total={seats.count()}, "
                f"gold={seats.filter(section='gold').count()}, "
                f"silver={seats.filter(section='silver').count()}"
            )

print("Finished.")


from cinema.models import Show, Seat

expected_sections = {
    "GA": ("gold", 10),
    "GB": ("gold", 8),
    "GC": ("gold", 10),
    "GD": ("gold", 17),
    "GE": ("gold", 19),
    "A": ("silver", 17),
    "B": ("silver", 15),
    "C": ("silver", 15),
    "D": ("silver", 15),
    "E": ("silver", 15),
    "F": ("silver", 15),
    "G": ("silver", 18),
    "H": ("silver", 18),
    "I": ("silver", 18),
    "J": ("silver", 18),
    "K": ("silver", 18),
    "L": ("silver", 12),
}

for show in Show.objects.all().order_by("id"):
    seats = Seat.objects.filter(show=show)

    gold_count = seats.filter(section="gold").count()
    silver_count = seats.filter(section="silver").count()

    print(f"\nShow {show.id}")
    print("Total:", seats.count())
    print("Gold:", gold_count, "| Price:", show.gold_price)
    print("Silver:", silver_count, "| Price:", show.silver_price)

    wrong_sections = []

    for prefix, (section, count) in expected_sections.items():
        for number in range(1, count + 1):
            label = f"{prefix}{number}"
            seat = seats.filter(seat_number=label).first()

            if seat is None:
                wrong_sections.append(f"{label}: MISSING")
            elif seat.section != section:
                wrong_sections.append(
                    f"{label}: expected {section}, got {seat.section}"
                )

    print("Section errors:", wrong_sections or "None")

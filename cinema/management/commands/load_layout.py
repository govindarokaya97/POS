from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from cinema.models import CinemaHall
from cinema.utils import parse_layout


class Command(BaseCommand):
    help = (
        "Create (or update) a cinema hall from a seat layout file.\n"
        "Example:  python manage.py load_layout \"Audi 1\" cinema/layouts/audi1.txt"
    )

    def add_arguments(self, parser):
        parser.add_argument("hall_name", help="Hall name, e.g. 'Audi 1'")
        parser.add_argument("layout_file", help="Path to the layout text file")

    def handle(self, *args, **options):
        path = Path(options["layout_file"])

        if not path.is_file():
            raise CommandError(f"File not found: {path}")

        text = path.read_text(encoding="utf-8")

        try:
            parse_layout(text)
        except ValueError as e:
            raise CommandError(f"Invalid layout: {e}")

        hall, created = CinemaHall.objects.get_or_create(
            name=options["hall_name"]
        )
        hall.layout = text
        hall.save()                      # total_seats is set from the layout

        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} hall '{hall.name}' "
            f"with {hall.total_seats} seats. "
            "Shows created from now on will use this layout "
            "(seats of existing shows are not changed)."
        ))

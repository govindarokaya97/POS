from django.db import migrations, models


def assign_existing_seat_sections(apps, schema_editor):
    Seat = apps.get_model("cinema", "Seat")
    Show = apps.get_model("cinema", "Show")
    db_alias = schema_editor.connection.alias

    shows = Show.objects.using(db_alias).select_related("hall").all()
    for show in shows.iterator():
        total_seats = show.hall.total_seats or 0
        total_rows = (total_seats + 9) // 10
        silver_rows = (total_rows + 1) // 2
        seats = Seat.objects.using(db_alias).filter(show_id=show.pk)
        for seat in seats.iterator():
            row_text = ""
            for char in seat.seat_number:
                if char.isalpha():
                    row_text += char.upper()
                else:
                    break
            row_index = 0
            for char in row_text:
                row_index = row_index * 26 + (ord(char) - ord("A") + 1)
            row_index = max(row_index - 1, 0)
            seat.section = "silver" if row_index < silver_rows else "gold"
            seat.save(update_fields=["section"])


class Migration(migrations.Migration):
    dependencies = [
        ("cinema", "0003_booking_ticket"),
    ]

    operations = [
        migrations.AlterField(
            model_name="show",
            name="ticket_price",
            field=models.DecimalField(
                decimal_places=2,
                default=300,
                help_text="Kept for compatibility. Ticket sales use fixed final prices: Gold Rs 400, Silver Rs 300, taxes included.",
                max_digits=10,
                verbose_name="Legacy ticket price (not used by Gold/Silver counter)",
            ),
        ),
        migrations.AddField(
            model_name="seat",
            name="section",
            field=models.CharField(
                choices=[("gold", "Gold"), ("silver", "Silver")],
                db_index=True,
                default="silver",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="local_tax_percent",
            field=models.DecimalField(decimal_places=2, default=3, max_digits=5),
        ),
        migrations.AddField(
            model_name="booking",
            name="local_tax",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
        migrations.RunPython(assign_existing_seat_sections, migrations.RunPython.noop),
    ]

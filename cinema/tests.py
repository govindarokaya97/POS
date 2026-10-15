from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Booking, CinemaHall, Movie, Seat, Show, Ticket
from .utils import generate_seats, seat_sort_key


class CinemaTestBase(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user("counter1", password="pw", is_staff=True)
        self.cashier = User.objects.create_user("plain", password="pw")

        self.hall = CinemaHall.objects.create(name="Hall 1", total_seats=25)

        # Long movie so a show starting at 00:00 today is still running.
        self.movie = Movie.objects.create(title="Test Movie", duration=60 * 48)

        self.today = timezone.localdate()

        # Show "today": used for entry verification.
        self.show = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today, start_time=time(0, 0),
            ticket_price=Decimal("300.00"),
        )
        generate_seats(self.show)

        self.client.force_login(self.staff)

    def seat(self, number, show=None):
        return Seat.objects.get(show=show or self.show, seat_number=number)

    def messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]

    def sell(self, seat_numbers, **extra):
        data = {"seats": [self.seat(n).id for n in seat_numbers]}
        data.update(extra)
        return self.client.post(
            reverse("ticket_checkout", args=[self.show.id]), data
        )


class SeatGenerationTests(CinemaTestBase):

    def test_seats_follow_hall_size(self):
        self.assertEqual(self.show.seats.count(), 25)
        numbers = sorted(
            self.show.seats.values_list("seat_number", flat=True),
            key=seat_sort_key,
        )
        self.assertEqual(numbers[0], "A1")
        self.assertEqual(numbers[9], "A10")
        self.assertEqual(numbers[10], "B1")
        self.assertEqual(numbers[-1], "C5")

    def test_generate_twice_is_harmless(self):
        generate_seats(self.show)
        self.assertEqual(self.show.seats.count(), 25)

    def test_natural_sort(self):
        self.assertLess(seat_sort_key("A2"), seat_sort_key("A10"))
        self.assertLess(seat_sort_key("A10"), seat_sort_key("B1"))


class AccessTests(CinemaTestBase):

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        r = self.client.get(reverse("cinema_dashboard"))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith(reverse("login") + "?next="))

    def test_non_staff_forbidden_everywhere(self):
        self.client.force_login(self.cashier)
        for name, args in [
            ("cinema_dashboard", []),
            ("seat_selection", [self.show.id]),
            ("ticket_checkout", [self.show.id]),
            ("booking_list", []),
            ("verify_ticket", []),
            ("cinema_report", []),
        ]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 403, name)

    def test_pages_render_for_staff(self):
        for name, args in [
            ("cinema_dashboard", []),
            ("seat_selection", [self.show.id]),
            ("booking_list", []),
            ("verify_ticket", []),
            ("cinema_report", []),
        ]:
            r = self.client.get(reverse(name, args=args))
            self.assertEqual(r.status_code, 200, name)


class CheckoutTests(CinemaTestBase):

    def test_checkout_requires_seats(self):
        r = self.client.get(reverse("ticket_checkout", args=[self.show.id]))
        self.assertRedirects(
            r, reverse("seat_selection", args=[self.show.id]),
            fetch_redirect_response=False,
        )

    def test_checkout_summary_renders(self):
        r = self.client.get(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("A2").id]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["subtotal"], Decimal("600.00"))

    def test_sale_with_discount_vat_and_change(self):
        r = self.sell(
            ["A1", "A2"],
            discount="50", vat_percent="13",
            payment_method="cash", paid_amount="700",
            customer_name="Ram", customer_phone="9800000000",
        )

        booking = Booking.objects.get()
        self.assertRedirects(
            r, f"{reverse('ticket_print', args=[booking.id])}?print=true",
            fetch_redirect_response=False,
        )

        self.assertEqual(booking.booking_number, f"BK-{booking.pk:05d}")
        self.assertEqual(booking.subtotal, Decimal("600.00"))
        self.assertEqual(booking.discount, Decimal("50.00"))
        self.assertEqual(booking.vat, Decimal("71.50"))      # 13% of 550
        self.assertEqual(booking.total, Decimal("621.50"))
        self.assertEqual(booking.paid_amount, Decimal("621.50"))
        self.assertEqual(booking.return_amount, Decimal("78.50"))
        self.assertEqual(booking.created_by, self.staff)
        self.assertEqual(booking.customer_name, "Ram")

        self.assertEqual(booking.tickets.count(), 2)
        self.assertEqual(
            sorted(t.ticket_number for t in booking.tickets.all()),
            [f"{booking.booking_number}-A1", f"{booking.booking_number}-A2"],
        )
        self.assertTrue(self.seat("A1").is_booked)
        self.assertTrue(self.seat("A2").is_booked)
        self.assertFalse(self.seat("A3").is_booked)

    def test_blank_received_means_exact(self):
        self.sell(["B1"], payment_method="esewa", paid_amount="")
        b = Booking.objects.get()
        self.assertEqual(b.total, Decimal("300.00"))
        self.assertEqual(b.return_amount, Decimal("0.00"))
        self.assertEqual(b.payment_method, "esewa")

    def test_cannot_sell_same_seat_twice(self):
        self.sell(["A1"])

        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("A2").id]},
            follow=True,
        )

        # Bounced back to the seat map with an explanation...
        self.assertEqual(r.redirect_chain[-1][0],
                         reverse("seat_selection", args=[self.show.id]))
        self.assertTrue(any("Already sold: A1" in m for m in self.messages(r)))
        # ...and nothing was half-sold.
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(self.seat("A2").is_booked)

    def test_race_lost_inside_transaction_sells_nothing(self):
        """Seat looked free on the checkout page but was sold before the
        POST landed (another counter). The locked re-check must refuse it."""
        stale_ids = [self.seat("A1").id, self.seat("A2").id]
        Seat.objects.filter(id=stale_ids[0]).update(is_booked=True)

        from django.test import RequestFactory
        from .views import BookingError, _create_booking
        from django.db import transaction

        req = RequestFactory().post("/", {"seats": stale_ids})
        req.user = self.staff
        with self.assertRaises(BookingError):
            with transaction.atomic():
                _create_booking(req, self.show)

        self.assertEqual(Booking.objects.count(), 0)
        self.assertFalse(self.seat("A2").is_booked)

    def test_underpayment_rejected(self):
        r = self.sell(["A1"], paid_amount="100")
        self.assertEqual(r.status_code, 200)            # form re-shown
        self.assertEqual(Booking.objects.count(), 0)
        self.assertFalse(self.seat("A1").is_booked)
        self.assertTrue(any("less than the total" in m for m in self.messages(r)))

    def test_bad_inputs_rejected(self):
        cases = [
            {"discount": "999"},                 # more than subtotal
            {"discount": "-5"},
            {"discount": "abc"},
            {"discount": "NaN"},
            {"vat_percent": "150"},
            {"payment_method": "bitcoin"},
            {"paid_amount": "-1"},
        ]
        for extra in cases:
            r = self.sell(["A1"], **extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertEqual(Booking.objects.count(), 0, extra)
            self.assertFalse(self.seat("A1").is_booked, extra)

    def test_invalid_seat_ids(self):
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": ["abc"]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    def test_seat_from_another_show_rejected(self):
        other = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today + timedelta(days=1), start_time=time(18, 0),
            ticket_price=Decimal("250.00"),
        )
        generate_seats(other)
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1", other).id]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    def test_ended_show_cannot_be_sold(self):
        short = Movie.objects.create(title="Short", duration=60)
        past = Show.objects.create(
            movie=short, hall=self.hall,
            show_date=self.today - timedelta(days=1), start_time=time(10, 0),
            ticket_price=Decimal("100.00"),
        )
        generate_seats(past)
        r = self.client.post(
            reverse("ticket_checkout", args=[past.id]),
            {"seats": [self.seat("A1", past).id]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    def test_default_vat_from_settings(self):
        with self.settings(CINEMA_VAT_PERCENT="13"):
            self.sell(["A1"])          # vat_percent omitted
        self.assertEqual(Booking.objects.get().vat, Decimal("39.00"))


class PrintTests(CinemaTestBase):

    def test_print_page_has_bill_tickets_and_barcodes(self):
        self.sell(["A1", "A2"])
        booking = Booking.objects.get()
        r = self.client.get(reverse("ticket_print", args=[booking.id]) + "?print=true")

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["auto_print"])
        html = r.content.decode()
        self.assertIn(booking.booking_number, html)
        self.assertIn(f"{booking.booking_number}-A1", html)
        self.assertIn(f"{booking.booking_number}-A2", html)
        self.assertEqual(html.count("ADMIT ONE"), 2)
        self.assertEqual(html.count('class="barcode"'), 2)
        for t in r.context["tickets"]:
            svg = str(t.barcode_svg)
            self.assertTrue(svg.startswith("<svg"))
            self.assertIn(svg, html)


class CancelTests(CinemaTestBase):

    def cancel(self, booking):
        return self.client.post(reverse("booking_cancel", args=[booking.id]))

    def test_cancel_releases_seats_and_allows_resale(self):
        self.sell(["A1", "A2"])
        booking = Booking.objects.get()

        self.cancel(booking)
        booking.refresh_from_db()

        self.assertTrue(booking.is_cancelled)
        self.assertEqual(booking.cancelled_by, self.staff)
        self.assertIsNotNone(booking.cancelled_at)
        self.assertFalse(self.seat("A1").is_booked)
        self.assertFalse(self.seat("A2").is_booked)

        # Same seat can be sold again with a fresh, distinct ticket number.
        self.sell(["A1"])
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 3)
        self.assertTrue(self.seat("A1").is_booked)

    def test_cancel_twice_does_nothing_more(self):
        self.sell(["A1"])
        booking = Booking.objects.get()
        self.cancel(booking)
        r = self.cancel(booking)
        self.assertTrue(any("already cancelled" in m for m in self.messages(r)))

    def test_cannot_cancel_after_entry_used(self):
        self.sell(["A1"])
        booking = Booking.objects.get()
        ticket = booking.tickets.get()
        self.client.post(reverse("verify_ticket"), {"ticket": ticket.ticket_number})

        self.cancel(booking)
        booking.refresh_from_db()
        self.assertFalse(booking.is_cancelled)
        self.assertTrue(self.seat("A1").is_booked)

    def test_cancel_requires_post(self):
        self.sell(["A1"])
        booking = Booking.objects.get()
        r = self.client.get(reverse("booking_cancel", args=[booking.id]))
        self.assertEqual(r.status_code, 405)


class VerifyTests(CinemaTestBase):

    def check(self, code):
        r = self.client.post(reverse("verify_ticket"), {"ticket": code})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_valid_then_already_used(self):
        self.sell(["A1"])
        number = Ticket.objects.get().ticket_number

        first = self.check(number)
        self.assertEqual(first["status"], "valid")
        self.assertEqual(first["seat"], "A1")
        self.assertTrue(Ticket.objects.get().used)

        second = self.check(number)
        self.assertEqual(second["status"], "already_used")

    def test_lowercase_scan_still_works(self):
        self.sell(["A1"])
        self.assertEqual(
            self.check(Ticket.objects.get().ticket_number.lower())["status"],
            "valid",
        )

    def test_invalid_and_empty(self):
        self.assertEqual(self.check("NOPE")["status"], "invalid")
        self.assertEqual(self.check("")["status"], "invalid")

    def test_cancelled_ticket_rejected(self):
        self.sell(["A1"])
        booking = Booking.objects.get()
        self.client.post(reverse("booking_cancel", args=[booking.id]))
        result = self.check(booking.tickets.get().ticket_number)
        self.assertEqual(result["status"], "cancelled")
        self.assertFalse(booking.tickets.get().used)

    def test_other_day_ticket_not_consumed(self):
        tomorrow = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today + timedelta(days=1), start_time=time(18, 0),
            ticket_price=Decimal("250.00"),
        )
        generate_seats(tomorrow)
        self.client.post(
            reverse("ticket_checkout", args=[tomorrow.id]),
            {"seats": [self.seat("A1", tomorrow).id]},
        )
        ticket = Ticket.objects.get()
        self.assertEqual(self.check(ticket.ticket_number)["status"], "wrong_date")
        self.assertFalse(Ticket.objects.get().used)


class BookingListAndReportTests(CinemaTestBase):

    def test_search_by_ticket_number_and_status_filter(self):
        self.sell(["A1"])
        self.sell(["A2"])
        first, second = Booking.objects.order_by("id")
        self.client.post(reverse("booking_cancel", args=[second.id]))

        r = self.client.get(reverse("booking_list"), {"q": f"{first.booking_number}-A1"})
        self.assertEqual([b.id for b in r.context["page"]], [first.id])

        r = self.client.get(reverse("booking_list"), {"status": "cancelled"})
        self.assertEqual([b.id for b in r.context["page"]], [second.id])

        r = self.client.get(reverse("booking_list"))
        self.assertEqual(len(r.context["page"]), 2)
        self.assertEqual(r.context["page"][0].ticket_count, 1)

    def test_report_totals_exclude_cancelled(self):
        self.sell(["A1", "A2"], payment_method="cash")      # 600
        self.sell(["B1"], payment_method="esewa")           # 300
        self.sell(["C1"], payment_method="cash")            # 300, cancelled
        cancelled = Booking.objects.order_by("id").last()
        self.client.post(reverse("booking_cancel", args=[cancelled.id]))

        r = self.client.get(reverse("cinema_report"))
        self.assertEqual(r.context["totals"]["total"], Decimal("900.00"))
        self.assertEqual(r.context["tickets_sold"], 3)
        self.assertEqual(r.context["cancelled_totals"]["total"], Decimal("300.00"))

        methods = {m["payment_method"]: m["total"] for m in r.context["by_method"]}
        self.assertEqual(methods, {"cash": Decimal("600.00"), "esewa": Decimal("300.00")})

    def test_dashboard_numbers(self):
        self.sell(["A1", "A2"])
        r = self.client.get(reverse("cinema_dashboard"))
        self.assertEqual(r.context["tickets_sold_today"], 2)
        self.assertEqual(r.context["revenue_today"], Decimal("600.00"))
        show = r.context["today_shows"][0]
        self.assertEqual((show.sold_count, show.seat_count), (2, 25))

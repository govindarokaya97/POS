from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking, CinemaHall, Movie, Seat, Show, Ticket
from .pricing import tax_breakdown
from .utils import generate_seats, seat_sort_key
from .views import BookingError, _create_sale

D = Decimal


class CinemaTestBase(TestCase):
    """Hall of 25 seats, 1 Gold row: A1-A10 and B1-B10 are Silver (Rs 300),
    C1-C5 are Gold (Rs 400)."""

    def setUp(self):
        self.staff = User.objects.create_user("counter1", password="pw", is_staff=True)
        self.cashier = User.objects.create_user("plain", password="pw")

        self.hall = CinemaHall.objects.create(
            name="Hall 1", total_seats=25, gold_rows=1
        )

        # Long movie so a show starting at 00:00 today is still running.
        self.movie = Movie.objects.create(title="Test Movie", duration=60 * 48)

        self.today = timezone.localdate()

        self.show = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today, start_time=time(0, 0),
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


# --------------------------------------------------------------------------
# Rules: sections, prices, taxes
# --------------------------------------------------------------------------

class PricingTests(TestCase):

    def test_gold_400_is_split_inside_the_price(self):
        b = tax_breakdown(D("400"))
        self.assertEqual(b["vat"], D("44.83"))          # 13% of the base
        self.assertEqual(b["local_tax"], D("10.34"))    # 3% of the base
        self.assertEqual(b["base"], D("344.83"))
        self.assertEqual(b["total"], D("400.00"))       # customer pays 400

    def test_silver_300_is_split_inside_the_price(self):
        b = tax_breakdown(D("300"))
        self.assertEqual(
            (b["base"], b["vat"], b["local_tax"], b["total"]),
            (D("258.62"), D("33.62"), D("7.76"), D("300.00")),
        )

    def test_parts_always_add_up_to_the_total(self):
        for price in ("400", "300", "250", "199.99", "1", "0.5"):
            b = tax_breakdown(D(price))
            self.assertEqual(b["base"] + b["vat"] + b["local_tax"], b["total"], price)

    def test_taxes_are_percent_of_base(self):
        b = tax_breakdown(D("400"))
        self.assertAlmostEqual(float(b["vat"] / b["base"]), 0.13, places=3)
        self.assertAlmostEqual(float(b["local_tax"] / b["base"]), 0.03, places=3)

    @override_settings(CINEMA_PRICES_INCLUDE_TAX=False)
    def test_taxes_on_top_when_switched(self):
        b = tax_breakdown(D("400"))
        self.assertEqual(
            (b["base"], b["vat"], b["local_tax"], b["total"]),
            (D("400.00"), D("52.00"), D("12.00"), D("464.00")),
        )


class SeatSectionTests(CinemaTestBase):

    def test_back_rows_are_gold_front_rows_silver(self):
        gold = set(self.show.seats.filter(section="gold").values_list("seat_number", flat=True))
        self.assertEqual(gold, {"C1", "C2", "C3", "C4", "C5"})
        self.assertEqual(self.show.seats.filter(section="silver").count(), 20)
        self.assertEqual(self.seat("A1").section, "silver")
        self.assertEqual(self.seat("B10").section, "silver")

    def test_default_hall_has_gold_at_back(self):
        hall = CinemaHall.objects.create(name="Big", total_seats=100)   # gold_rows=3
        show = Show.objects.create(
            movie=self.movie, hall=hall,
            show_date=self.today, start_time=time(1, 0),
        )
        generate_seats(show)
        self.assertEqual(show.seats.filter(section="gold").count(), 30)  # rows H, I, J
        self.assertEqual(Seat.objects.get(show=show, seat_number="H1").section, "gold")
        self.assertEqual(Seat.objects.get(show=show, seat_number="G10").section, "silver")

    def test_all_gold_or_none(self):
        none = CinemaHall.objects.create(name="N", total_seats=20, gold_rows=0)
        all_ = CinemaHall.objects.create(name="A", total_seats=20, gold_rows=99)
        for hall, expected in ((none, 0), (all_, 20)):
            show = Show.objects.create(
                movie=self.movie, hall=hall,
                show_date=self.today, start_time=time(2, 0),
            )
            generate_seats(show)
            self.assertEqual(show.seats.filter(section="gold").count(), expected)

    def test_default_prices(self):
        self.assertEqual(self.show.gold_price, D("400.00"))
        self.assertEqual(self.show.silver_price, D("300.00"))
        self.assertEqual(self.show.price_for("gold"), D("400.00"))
        self.assertEqual(self.show.price_for("silver"), D("300.00"))

    def test_generate_twice_is_harmless_and_keeps_sections(self):
        generate_seats(self.show)
        self.assertEqual(self.show.seats.count(), 25)
        self.assertEqual(self.show.seats.filter(section="gold").count(), 5)

    def test_natural_sort(self):
        self.assertLess(seat_sort_key("A2"), seat_sort_key("A10"))


# --------------------------------------------------------------------------
# Access
# --------------------------------------------------------------------------

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
            ("sale_print", ["SL-X"]),
            ("booking_list", []),
            ("verify_ticket", []),
            ("cinema_report", []),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)

    def test_pages_render_for_staff(self):
        for name, args in [
            ("cinema_dashboard", []),
            ("seat_selection", [self.show.id]),
            ("booking_list", []),
            ("verify_ticket", []),
            ("cinema_report", []),
        ]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200, name)

    def test_seat_map_shows_both_sections_with_prices(self):
        r = self.client.get(reverse("seat_selection", args=[self.show.id]))
        html = r.content.decode()
        self.assertIn("Gold", html)
        self.assertIn("Silver", html)
        starts = [row["section"] for row in r.context["rows"] if row["starts_section"]]
        self.assertEqual(starts, ["silver", "gold"])
        prices = {row["section"]: row["price"] for row in r.context["rows"]}
        self.assertEqual(prices, {"silver": D("300.00"), "gold": D("400.00")})


# --------------------------------------------------------------------------
# Sale: one seat = one invoice
# --------------------------------------------------------------------------

class CheckoutTests(CinemaTestBase):

    def test_checkout_requires_seats(self):
        r = self.client.get(reverse("ticket_checkout", args=[self.show.id]))
        self.assertRedirects(
            r, reverse("seat_selection", args=[self.show.id]),
            fetch_redirect_response=False,
        )

    def test_checkout_preview_per_seat_and_totals(self):
        r = self.client.get(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("C1").id]},
        )
        self.assertEqual(r.status_code, 200)
        silver, gold = r.context["lines"]
        self.assertEqual((silver["section"], silver["total"]), ("silver", D("300.00")))
        self.assertEqual((gold["section"], gold["total"]), ("gold", D("400.00")))
        self.assertEqual(r.context["totals"]["total"], D("700.00"))
        self.assertEqual(r.context["totals"]["vat"], D("78.45"))        # 44.83 + 33.62
        self.assertEqual(r.context["totals"]["local_tax"], D("18.10"))  # 10.34 + 7.76

    def test_each_seat_gets_its_own_invoice(self):
        r = self.sell(["A1", "A2", "C1"], paid_amount="1000")

        bookings = list(Booking.objects.order_by("id"))
        self.assertEqual(len(bookings), 3)

        # Three separate invoices, each with exactly one ticket / one seat.
        self.assertEqual(len({b.booking_number for b in bookings}), 3)
        for b in bookings:
            self.assertEqual(b.tickets.count(), 1)

        # They belong to one counter sale and print together.
        refs = {b.sale_ref for b in bookings}
        self.assertEqual(len(refs), 1)
        self.assertRedirects(
            r, f"{reverse('sale_print', args=[refs.pop()])}?print=true",
            fetch_redirect_response=False,
        )

        for n in ("A1", "A2", "C1"):
            self.assertTrue(self.seat(n).is_booked, n)
        self.assertFalse(self.seat("A3").is_booked)

    def test_silver_invoice_amounts(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        t = b.tickets.get()
        self.assertEqual(t.section, "silver")
        self.assertEqual(t.price, D("300.00"))
        self.assertEqual(
            (b.subtotal, b.vat, b.local_tax, b.total),
            (D("258.62"), D("33.62"), D("7.76"), D("300.00")),
        )
        self.assertEqual((b.vat_percent, b.local_tax_percent), (D("13.00"), D("3.00")))
        self.assertEqual(b.paid_amount, D("300.00"))
        self.assertEqual(b.created_by, self.staff)

    def test_gold_invoice_amounts(self):
        self.sell(["C3"])
        b = Booking.objects.get()
        t = b.tickets.get()
        self.assertEqual(t.section, "gold")
        self.assertEqual(t.price, D("400.00"))
        self.assertEqual(
            (b.subtotal, b.vat, b.local_tax, b.total),
            (D("344.83"), D("44.83"), D("10.34"), D("400.00")),
        )

    def test_mixed_sale_each_invoice_has_its_own_section_price(self):
        self.sell(["A1", "C1"])
        totals = {b.tickets.get().seat.seat_number: b.total for b in Booking.objects.all()}
        self.assertEqual(totals, {"A1": D("300.00"), "C1": D("400.00")})

    def test_ticket_numbers(self):
        self.sell(["A1", "C1"])
        for b in Booking.objects.all():
            seat = b.tickets.get().seat.seat_number
            self.assertEqual(b.tickets.get().ticket_number, f"{b.booking_number}-{seat}")

    def test_change_is_reported_not_stored_per_invoice(self):
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("C1").id], "paid_amount": "1000"},
            follow=True,
        )
        text = " ".join(self.messages(r))
        self.assertIn("2 invoice(s) created", text)
        self.assertIn("Return change: Rs 300.00", text)   # 1000 - (300 + 400)
        self.assertTrue(all(b.paid_amount == b.total for b in Booking.objects.all()))

    def test_blank_received_means_exact(self):
        self.sell(["B1"], payment_method="esewa", paid_amount="")
        self.assertEqual(Booking.objects.get().payment_method, "esewa")

    def test_client_cannot_change_price_or_tax(self):
        self.sell(["A1"], discount="250", vat_percent="0", local_tax_percent="0",
                  ticket_price="1", gold_price="1")
        b = Booking.objects.get()
        self.assertEqual(b.total, D("300.00"))
        self.assertEqual((b.vat_percent, b.local_tax_percent), (D("13.00"), D("3.00")))
        self.assertEqual(b.discount, D("0.00"))

    def test_cannot_sell_same_seat_twice(self):
        self.sell(["A1"])
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("A2").id]},
            follow=True,
        )
        self.assertEqual(r.redirect_chain[-1][0],
                         reverse("seat_selection", args=[self.show.id]))
        self.assertTrue(any("Already sold: A1" in m for m in self.messages(r)))
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(self.seat("A2").is_booked)

    def test_race_lost_inside_transaction_sells_nothing(self):
        ids = [self.seat("A1").id, self.seat("A2").id]
        Seat.objects.filter(id=ids[0]).update(is_booked=True)

        req = RequestFactory().post("/", {"seats": ids})
        req.user = self.staff
        with self.assertRaises(BookingError):
            with transaction.atomic():
                _create_sale(req, self.show)

        self.assertEqual(Booking.objects.count(), 0)
        self.assertFalse(self.seat("A2").is_booked)

    def test_underpayment_rejected_and_nothing_created(self):
        r = self.sell(["A1", "C1"], paid_amount="699")      # total is 700
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertFalse(self.seat("A1").is_booked)
        self.assertTrue(any("less than the total" in m for m in self.messages(r)))

    def test_bad_inputs_rejected(self):
        for extra in ({"payment_method": "bitcoin"}, {"paid_amount": "-1"},
                      {"paid_amount": "abc"}, {"paid_amount": "NaN"}):
            r = self.sell(["A1"], **extra)
            self.assertEqual(r.status_code, 200, extra)
            self.assertEqual(Booking.objects.count(), 0, extra)
            self.assertFalse(self.seat("A1").is_booked, extra)

    def test_invalid_seat_ids(self):
        r = self.client.post(reverse("ticket_checkout", args=[self.show.id]), {"seats": ["abc"]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    def test_seat_from_another_show_rejected(self):
        other = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today + timedelta(days=1), start_time=time(18, 0),
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
        )
        generate_seats(past)
        r = self.client.post(
            reverse("ticket_checkout", args=[past.id]),
            {"seats": [self.seat("A1", past).id]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Booking.objects.count(), 0)

    @override_settings(CINEMA_PRICES_INCLUDE_TAX=False)
    def test_tax_on_top_mode_charges_more(self):
        self.sell(["C1"])
        self.assertEqual(Booking.objects.get().total, D("464.00"))


# --------------------------------------------------------------------------
# Printing: one slip per seat
# --------------------------------------------------------------------------

class PrintTests(CinemaTestBase):

    def test_sale_prints_one_slip_per_seat(self):
        self.sell(["A1", "A2", "C1"])
        ref = Booking.objects.first().sale_ref
        r = self.client.get(reverse("sale_print", args=[ref]) + "?print=true")

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["auto_print"])
        self.assertEqual(len(r.context["slips"]), 3)

        html = r.content.decode()
        self.assertEqual(html.count('class="slip"'), 3)
        self.assertEqual(html.count('class="barcode"'), 3)
        self.assertEqual(html.count("SILVER</p>"), 2)
        self.assertEqual(html.count("GOLD</p>"), 1)
        self.assertEqual(html.count("VAT (13%)"), 3)
        self.assertEqual(html.count("Local Tax (3%)"), 3)
        for b in Booking.objects.all():
            self.assertIn(b.booking_number, html)

    def test_slip_shows_the_breakdown(self):
        self.sell(["C1"])
        b = Booking.objects.get()
        html = self.client.get(reverse("ticket_print", args=[b.id])).content.decode()
        for text in ("344.83", "44.83", "10.34", "400.00", "TAX INVOICE"):
            self.assertIn(text, html)

    def test_single_reprint_is_one_slip(self):
        self.sell(["A1", "A2"])
        b = Booking.objects.order_by("id").first()
        r = self.client.get(reverse("ticket_print", args=[b.id]))
        self.assertEqual(r.content.decode().count('class="slip"'), 1)
        self.assertTrue(r.context["single"])

    def test_barcode_is_in_the_page(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        r = self.client.get(reverse("ticket_print", args=[b.id]))
        svg = str(r.context["slips"][0]["ticket"].barcode_svg)
        self.assertTrue(svg.startswith("<svg"))
        self.assertIn(svg, r.content.decode())

    def test_unknown_sale_redirects(self):
        r = self.client.get(reverse("sale_print", args=["SL-NOPE"]))
        self.assertRedirects(r, reverse("cinema_dashboard"), fetch_redirect_response=False)


# --------------------------------------------------------------------------
# Cancel + verify
# --------------------------------------------------------------------------

class CancelTests(CinemaTestBase):

    def cancel(self, booking):
        return self.client.post(reverse("booking_cancel", args=[booking.id]))

    def test_cancel_one_invoice_leaves_the_others(self):
        self.sell(["A1", "A2"])
        first, second = Booking.objects.order_by("id")
        self.cancel(first)
        first.refresh_from_db(); second.refresh_from_db()

        self.assertTrue(first.is_cancelled)
        self.assertEqual(first.cancelled_by, self.staff)
        self.assertFalse(second.is_cancelled)
        self.assertFalse(self.seat("A1").is_booked)
        self.assertTrue(self.seat("A2").is_booked)

    def test_cancelled_seat_can_be_resold(self):
        self.sell(["C1"])
        self.cancel(Booking.objects.get())
        self.sell(["C1"])
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertTrue(self.seat("C1").is_booked)

    def test_cancel_twice(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        self.cancel(b)
        r = self.cancel(b)
        self.assertTrue(any("already cancelled" in m for m in self.messages(r)))

    def test_cannot_cancel_after_entry_used(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        self.client.post(reverse("verify_ticket"), {"ticket": b.tickets.get().ticket_number})
        self.cancel(b)
        b.refresh_from_db()
        self.assertFalse(b.is_cancelled)
        self.assertTrue(self.seat("A1").is_booked)

    def test_cancel_requires_post(self):
        self.sell(["A1"])
        r = self.client.get(reverse("booking_cancel", args=[Booking.objects.get().id]))
        self.assertEqual(r.status_code, 405)


class VerifyTests(CinemaTestBase):

    def check(self, code):
        r = self.client.post(reverse("verify_ticket"), {"ticket": code})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_valid_then_already_used_and_reports_section(self):
        self.sell(["C2"])
        number = Ticket.objects.get().ticket_number
        first = self.check(number)
        self.assertEqual(first["status"], "valid")
        self.assertEqual((first["seat"], first["section"]), ("C2", "Gold"))
        self.assertEqual(self.check(number)["status"], "already_used")

    def test_lowercase_scan_still_works(self):
        self.sell(["A1"])
        self.assertEqual(self.check(Ticket.objects.get().ticket_number.lower())["status"], "valid")

    def test_invalid_and_empty(self):
        self.assertEqual(self.check("NOPE")["status"], "invalid")
        self.assertEqual(self.check("")["status"], "invalid")

    def test_cancelled_ticket_rejected(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        self.client.post(reverse("booking_cancel", args=[b.id]))
        self.assertEqual(self.check(b.tickets.get().ticket_number)["status"], "cancelled")
        self.assertFalse(b.tickets.get().used)

    def test_other_day_ticket_not_consumed(self):
        tomorrow = Show.objects.create(
            movie=self.movie, hall=self.hall,
            show_date=self.today + timedelta(days=1), start_time=time(18, 0),
        )
        generate_seats(tomorrow)
        self.client.post(
            reverse("ticket_checkout", args=[tomorrow.id]),
            {"seats": [self.seat("A1", tomorrow).id]},
        )
        ticket = Ticket.objects.get()
        self.assertEqual(self.check(ticket.ticket_number)["status"], "wrong_date")
        self.assertFalse(Ticket.objects.get().used)


# --------------------------------------------------------------------------
# Lists + report
# --------------------------------------------------------------------------

class BookingListAndReportTests(CinemaTestBase):

    def test_search_by_ticket_number_and_status_filter(self):
        self.sell(["A1"]); self.sell(["A2"])
        first, second = Booking.objects.order_by("id")
        self.client.post(reverse("booking_cancel", args=[second.id]))

        r = self.client.get(reverse("booking_list"), {"q": f"{first.booking_number}-A1"})
        self.assertEqual([b.id for b in r.context["page"]], [first.id])

        r = self.client.get(reverse("booking_list"), {"status": "cancelled"})
        self.assertEqual([b.id for b in r.context["page"]], [second.id])

        r = self.client.get(reverse("booking_list"))
        self.assertEqual(len(r.context["page"]), 2)

    def test_report_totals_taxes_and_sections(self):
        self.sell(["A1", "C1"], payment_method="cash")     # 300 + 400
        self.sell(["B1"], payment_method="esewa")          # 300
        self.sell(["C2"], payment_method="cash")           # 400, then cancelled
        self.client.post(reverse("booking_cancel", args=[Booking.objects.order_by("id").last().id]))

        r = self.client.get(reverse("cinema_report"))
        t = r.context["totals"]
        self.assertEqual(t["bookings"], 3)
        self.assertEqual(t["total"], D("1000.00"))
        self.assertEqual(t["vat"], D("112.07"))            # 44.83 + 33.62 + 33.62
        self.assertEqual(t["local_tax"], D("25.86"))       # 10.34 + 7.76 + 7.76
        self.assertEqual(t["subtotal"], D("862.07"))
        self.assertEqual(t["subtotal"] + t["vat"] + t["local_tax"], t["total"])
        self.assertEqual(r.context["tickets_sold"], 3)
        self.assertEqual(r.context["cancelled_totals"]["total"], D("400.00"))

        sections = {s["section"]: (s["tickets"], s["total"]) for s in r.context["by_section"]}
        self.assertEqual(sections, {"gold": (1, D("400.00")), "silver": (2, D("600.00"))})

        methods = {m["payment_method"]: m["total"] for m in r.context["by_method"]}
        self.assertEqual(methods, {"cash": D("700.00"), "esewa": D("300.00")})

    def test_dashboard_numbers(self):
        self.sell(["A1", "C1"])
        r = self.client.get(reverse("cinema_dashboard"))
        self.assertEqual(r.context["tickets_sold_today"], 2)
        self.assertEqual(r.context["revenue_today"], D("700.00"))
        self.assertEqual(r.context["bookings_today"], 2)
        show = r.context["today_shows"][0]
        self.assertEqual((show.sold_count, show.seat_count), (2, 25))

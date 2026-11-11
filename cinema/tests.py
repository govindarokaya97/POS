from datetime import time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Booking, CinemaHall, Movie, Seat, Show, Ticket
from billing.models import ShopSetting

from .pricing import tax_breakdown
from .utils import generate_seats, seat_sort_key
from .views import BookingError, _create_sale

D = Decimal


class CinemaTestBase(TestCase):
    """Hall of 25 seats, 1 Gold row: A1-A10 and B1-B10 are Silver (Rs 300),
    GA1-C5 are Gold (Rs 400)."""

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

    def test_silver_300_matches_the_printed_sample_invoice(self):
        b = tax_breakdown(D("300"))
        self.assertEqual(
            (b["base"], b["vat"], b["local_tax"], b["total"]),
            (D("257.76"), D("34.51"), D("7.73"), D("300.00")),
        )

    def test_gold_400_is_split_inside_the_price(self):
        b = tax_breakdown(D("400"))
        self.assertEqual(
            (b["base"], b["vat"], b["local_tax"], b["total"]),
            (D("343.67"), D("46.02"), D("10.31"), D("400.00")),
        )

    def test_parts_always_add_up_to_the_total(self):
        for price in ("400", "300", "250", "199.99", "1", "0.5", "1234.56"):
            b = tax_breakdown(D(price))
            self.assertEqual(b["base"] + b["vat"] + b["local_tax"], b["total"], price)

    def test_local_tax_on_base_and_vat_on_base_plus_local(self):
        b = tax_breakdown(D("400"))
        self.assertAlmostEqual(float(b["local_tax"] / b["base"]), 0.03, places=3)
        self.assertAlmostEqual(
            float(b["vat"] / (b["base"] + b["local_tax"])), 0.13, places=3
        )

    @override_settings(CINEMA_PRICES_INCLUDE_TAX=False)
    def test_taxes_on_top_when_switched(self):
        b = tax_breakdown(D("400"))
        self.assertEqual(
            (b["base"], b["local_tax"], b["vat"], b["total"]),
            (D("400.00"), D("12.00"), D("53.56"), D("465.56")),
        )


class SeatSectionTests(CinemaTestBase):

    def test_gold_rows_come_first_named_with_g_silver_after(self):
        gold = set(self.show.seats.filter(section="gold").values_list("seat_number", flat=True))
        self.assertEqual(gold, {f"GA{i}" for i in range(1, 11)})
        self.assertEqual(self.show.seats.filter(section="silver").count(), 15)
        self.assertEqual(self.seat("A1").section, "silver")
        self.assertEqual(self.seat("B5").section, "silver")
        self.assertEqual(self.seat("GA1").row_index, 0)      # back row = top
        self.assertEqual(self.seat("A1").row_index, 1)

    def test_default_hall_has_three_gold_rows(self):
        hall = CinemaHall.objects.create(name="Big", total_seats=100)   # gold_rows=3
        show = Show.objects.create(
            movie=self.movie, hall=hall, show_date=self.today, start_time=time(1, 0),
        )
        generate_seats(show)
        self.assertEqual(show.seats.filter(section="gold").count(), 30)
        self.assertEqual(Seat.objects.get(show=show, seat_number="GC10").section, "gold")
        self.assertEqual(Seat.objects.get(show=show, seat_number="G10").section, "silver")

    def test_all_gold_or_none(self):
        none = CinemaHall.objects.create(name="N", total_seats=20, gold_rows=0)
        all_ = CinemaHall.objects.create(name="A", total_seats=20, gold_rows=99)
        for hall, expected in ((none, 0), (all_, 20)):
            show = Show.objects.create(
                movie=self.movie, hall=hall, show_date=self.today, start_time=time(2, 0),
            )
            generate_seats(show)
            self.assertEqual(show.seats.filter(section="gold").count(), expected)

    def test_default_prices(self):
        self.assertEqual(self.show.price_for("gold"), D("400.00"))
        self.assertEqual(self.show.price_for("silver"), D("300.00"))

    def test_generate_twice_is_harmless(self):
        generate_seats(self.show)
        self.assertEqual(self.show.seats.count(), 25)
        self.assertEqual(self.show.seats.filter(section="gold").count(), 10)

    def test_natural_sort(self):
        self.assertLess(seat_sort_key("A2"), seat_sort_key("A10"))
        self.assertLess(seat_sort_key("GA9"), seat_sort_key("GB1"))


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
        self.assertIn("SCREEN THIS WAY", html)
        starts = [row["section"] for row in r.context["rows"] if row.get("starts_section")]
        self.assertEqual(starts, ["gold", "silver"])
        prices = {row["section"]: row["price"] for row in r.context["rows"] if not row["is_gap"]}
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
            {"seats": [self.seat("A1").id, self.seat("GA1").id]},
        )
        self.assertEqual(r.status_code, 200)
        silver, gold = r.context["lines"]
        self.assertEqual((silver["section"], silver["total"]), ("silver", D("300.00")))
        self.assertEqual((gold["section"], gold["total"]), ("gold", D("400.00")))
        self.assertEqual(r.context["totals"]["total"], D("700.00"))
        self.assertEqual(r.context["totals"]["vat"], D("80.53"))        # 34.51 + 46.02
        self.assertEqual(r.context["totals"]["local_tax"], D("18.04"))  # 7.73 + 10.31
        self.assertEqual(r.context["totals"]["base"], D("601.43"))

    def test_each_seat_gets_its_own_invoice(self):
        r = self.sell(["A1", "A2", "GA1"], paid_amount="1000")

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

        for n in ("A1", "A2", "GA1"):
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
            (D("257.76"), D("34.51"), D("7.73"), D("300.00")),
        )
        self.assertEqual((b.vat_percent, b.local_tax_percent), (D("13.00"), D("3.00")))
        self.assertEqual(b.paid_amount, D("300.00"))
        self.assertEqual(b.created_by, self.staff)

    def test_gold_invoice_amounts(self):
        self.sell(["GA3"])
        b = Booking.objects.get()
        t = b.tickets.get()
        self.assertEqual(t.section, "gold")
        self.assertEqual(t.price, D("400.00"))
        self.assertEqual(
            (b.subtotal, b.vat, b.local_tax, b.total),
            (D("343.67"), D("46.02"), D("10.31"), D("400.00")),
        )

    def test_mixed_sale_each_invoice_has_its_own_section_price(self):
        self.sell(["A1", "GA1"])
        totals = {b.tickets.get().seat.seat_number: b.total for b in Booking.objects.all()}
        self.assertEqual(totals, {"A1": D("300.00"), "GA1": D("400.00")})

    def test_ticket_numbers(self):
        self.sell(["A1", "GA1"])
        for b in Booking.objects.all():
            seat = b.tickets.get().seat.seat_number
            self.assertEqual(b.tickets.get().ticket_number, f"{b.booking_number}-{seat}")

    def test_change_is_reported_not_stored_per_invoice(self):
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("GA1").id], "paid_amount": "1000"},
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
        r = self.sell(["A1", "GA1"], paid_amount="699")      # total is 700
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
        self.sell(["GA1"])
        self.assertEqual(Booking.objects.get().total, D("465.56"))


# --------------------------------------------------------------------------
# Printing: one slip per seat
# --------------------------------------------------------------------------

class PrintTests(CinemaTestBase):

    def test_sale_prints_one_slip_per_seat(self):
        self.sell(["A1", "A2", "GA1"])
        ref = Booking.objects.first().sale_ref
        r = self.client.get(reverse("sale_print", args=[ref]) + "?print=true")

        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["auto_print"])
        self.assertEqual(len(r.context["slips"]), 3)

        html = r.content.decode()
        self.assertEqual(html.count('class="slip"'), 3)
        self.assertEqual(html.count('class="qr"'), 3)
        self.assertEqual(html.count("· Silver"), 2)
        self.assertEqual(html.count("· Gold"), 1)
        self.assertEqual(html.count("VAT (13.00%)"), 3)
        self.assertEqual(html.count("Local Tax (3.00%)"), 3)
        for b in Booking.objects.all():
            self.assertIn(b.booking_number, html)

    def test_slip_matches_the_sample_invoice_layout(self):
        self.movie.grade = "PG"
        self.movie.save()
        ShopSetting.objects.create(shop_name="skcinemas", address="Pahalmanpur", vat_number="609123045")
        self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("B5").id]},
        )
        b = Booking.objects.get()
        t = b.tickets.get()
        html = self.client.get(reverse("ticket_print", args=[b.id])).content.decode()

        for text in (
            "skcinemas", "Pahalmanpur", "VAT 609123045", "INVOICE",
            "S.No.", b.booking_number, "Test Movie", "Grade PG - 2D",
            "Hall 1 · Silver", "HS Code", ": 00",
            "DATE", "TIME", "SEAT", ">B5<",
            "Entrance Fee", "Rs. 257.76", "VAT (13.00%)", "Rs. 34.51",
            "Local Tax (3.00%)", "Rs. 7.73", "Total Cost", "Rs. 300",
            "In words: Three Hundred Rupees Only",
            t.code, "Terms and Conditions", "Tickets non-refunded.",
            "Seats non-alterable.", "Issued At", "Device", "BOX OFFICE 1",
            "Issued By", "counter1", "Enjoy your movie at skcinemas",
        ):
            self.assertIn(text, html, text)

    def test_single_reprint_is_one_slip(self):
        self.sell(["A1", "A2"])
        b = Booking.objects.order_by("id").first()
        r = self.client.get(reverse("ticket_print", args=[b.id]))
        self.assertEqual(r.content.decode().count('class="slip"'), 1)
        self.assertTrue(r.context["single"])

    def test_qr_code_is_printed_and_decodes_to_the_ticket_code(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        r = self.client.get(reverse("ticket_print", args=[b.id]))
        svg = str(r.context["slips"][0]["ticket"].code_svg)
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
        self.sell(["GA1"])
        self.cancel(Booking.objects.get())
        self.sell(["GA1"])
        self.assertEqual(Booking.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertTrue(self.seat("GA1").is_booked)

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
        self.sell(["GA2"])
        number = Ticket.objects.get().code
        first = self.check(number)
        self.assertEqual(first["status"], "valid")
        self.assertEqual((first["seat"], first["section"]), ("GA2", "Gold"))
        self.assertEqual(self.check(number)["status"], "already_used")

    def test_scanning_the_qr_code_works_in_any_case(self):
        self.sell(["A1"])
        self.assertEqual(self.check(Ticket.objects.get().code.lower())["status"], "valid")

    def test_ticket_number_still_accepted(self):
        self.sell(["A1"])
        self.assertEqual(self.check(Ticket.objects.get().ticket_number)["status"], "valid")

    def test_invalid_and_empty(self):
        self.assertEqual(self.check("NOPE")["status"], "invalid")
        self.assertEqual(self.check("")["status"], "invalid")

    def test_cancelled_ticket_rejected(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        self.client.post(reverse("booking_cancel", args=[b.id]))
        self.assertEqual(self.check(b.tickets.get().code)["status"], "cancelled")
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
        self.assertEqual(self.check(ticket.code)["status"], "wrong_date")
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
        self.sell(["A1", "GA1"], payment_method="cash")     # 300 + 400
        self.sell(["B1"], payment_method="esewa")          # 300
        self.sell(["GA2"], payment_method="cash")           # 400, then cancelled
        self.client.post(reverse("booking_cancel", args=[Booking.objects.order_by("id").last().id]))

        r = self.client.get(reverse("cinema_report"))
        t = r.context["totals"]
        self.assertEqual(t["bookings"], 3)
        self.assertEqual(t["total"], D("1000.00"))
        self.assertEqual(t["vat"], D("115.04"))            # 34.51 + 46.02 + 34.51
        self.assertEqual(t["local_tax"], D("25.77"))       # 7.73 + 10.31 + 7.73
        self.assertEqual(t["subtotal"], D("859.19"))
        self.assertEqual(t["subtotal"] + t["vat"] + t["local_tax"], t["total"])
        self.assertEqual(r.context["tickets_sold"], 3)
        self.assertEqual(r.context["cancelled_totals"]["total"], D("400.00"))

        sections = {s["section"]: (s["tickets"], s["total"]) for s in r.context["by_section"]}
        self.assertEqual(sections, {"gold": (1, D("400.00")), "silver": (2, D("600.00"))})

        methods = {m["payment_method"]: m["total"] for m in r.context["by_method"]}
        self.assertEqual(methods, {"cash": D("700.00"), "esewa": D("300.00")})

    def test_dashboard_numbers(self):
        self.sell(["A1", "GA1"])
        r = self.client.get(reverse("cinema_dashboard"))
        self.assertEqual(r.context["tickets_sold_today"], 2)
        self.assertEqual(r.context["revenue_today"], D("700.00"))
        self.assertEqual(r.context["bookings_today"], 2)
        show = r.context["today_shows"][0]
        self.assertEqual((show.sold_count, show.seat_count), (2, 25))


# --------------------------------------------------------------------------
# Hall layout (aisles, GA-GE gold, A-L silver) + ticket code + words
# --------------------------------------------------------------------------

from pathlib import Path

from .utils import amount_in_words, parse_layout


class LayoutTests(CinemaTestBase):

    def test_parse_rows_gaps_comments(self):
        rows = parse_layout("# hi\nGA gold oo..o\n\ngap\nA silver ooo  # back\n")
        self.assertEqual(
            rows,
            [
                {"gap": False, "label": "GA", "section": "gold", "pattern": "oo..o"},
                {"gap": True},
                {"gap": False, "label": "A", "section": "silver", "pattern": "ooo"},
            ],
        )

    def test_bad_layouts_are_rejected_with_the_line_number(self):
        for text, fragment in (
            ("A silver", "Line 1"),
            ("A bronze ooo", "gold' or 'silver"),
            ("A silver oxo", "'o' (seat)"),
            ("A silver ...", "no seats"),
            ("A silver ooo\nA gold ooo", "Line 2: row 'A' is used twice"),
            ("1 silver ooo", "1-3 letters"),
        ):
            with self.assertRaises(ValueError) as cm:
                parse_layout(text)
            self.assertIn(fragment, str(cm.exception), text)

    def test_audi1_layout_from_the_screenshots(self):
        text = (Path(__file__).parent / "layouts" / "audi1.txt").read_text()
        rows = parse_layout(text)

        seat_rows = [r for r in rows if not r["gap"]]
        self.assertEqual([r["label"] for r in seat_rows],
                         ["GA", "GB", "GC", "GD", "GE", "A", "B", "C", "D", "E",
                          "F", "G", "H", "I", "J", "K", "L"])
        self.assertEqual({len(r["pattern"]) for r in seat_rows}, {20})
        counts = {r["label"]: r["pattern"].count("o") for r in seat_rows}
        # Row sizes confirmed by the cinema.
        self.assertEqual(counts, {
            "GA": 10, "GB": 8, "GC": 10, "GD": 17, "GE": 19,
            "A": 17, "B": 15, "C": 15, "D": 15, "E": 15, "F": 15,
            "G": 18, "H": 18, "I": 18, "J": 18, "K": 18, "L": 12,
        })

        hall = CinemaHall.objects.create(name="Audi 1", layout=text)
        self.assertEqual(hall.total_seats, 258)              # set from the layout

        show = Show.objects.create(
            movie=self.movie, hall=hall, show_date=self.today, start_time=time(3, 0),
        )
        generate_seats(show)
        self.assertEqual(show.seats.count(), 258)
        self.assertEqual(show.seats.filter(section="gold").count(), 64)
        self.assertEqual(show.seats.filter(section="silver").count(), 194)

    def test_seat_numbers_and_positions_follow_the_layout(self):
        hall = CinemaHall.objects.create(
            name="Mini", layout="GA gold oo...oo\ngap\nA silver .ooo.oo\n"
        )
        show = Show.objects.create(
            movie=self.movie, hall=hall, show_date=self.today, start_time=time(4, 0),
        )
        generate_seats(show)
        pos = {s.seat_number: (s.row_index, s.col_index) for s in show.seats.all()}
        self.assertEqual(pos["GA1"], (0, 0))
        self.assertEqual(pos["GA3"], (0, 5))          # numbered across the aisle
        self.assertEqual(pos["A1"], (2, 1))           # row 1 is the walkway
        self.assertEqual(pos["A5"], (2, 6))
        self.assertEqual(hall.total_seats, 9)



    def test_seat_map_keeps_aisles_and_walkway(self):
        hall = CinemaHall.objects.create(
            name="Mini",
            layout="GA gold oo...oo\ngap\nA silver .ooo.oo\n",
        )
        show = Show.objects.create(
            movie=self.movie,
            hall=hall,
            show_date=self.today,
            start_time=time(4, 0),
        )

        response = self.client.get(
            reverse("seat_selection", args=[show.id])
        )
        rows = response.context["rows"]

        self.assertEqual(
            [row["is_gap"] for row in rows],
            [False, True, False],
        )

        ga = [
            cell.seat_number if cell else None
            for cell in rows[0]["cells"]
        ]
        self.assertEqual(
            ga,
            ["GA1", "GA2", None, None, None, "GA3", "GA4"],
        )

        a = [
            cell.seat_number if cell else None
            for cell in rows[2]["cells"]
        ]
        self.assertEqual(
            a,
            [None, "A1", "A2", "A3", None, "A4", "A5"],
        )



    def test_seat_map_keeps_walkways_when_physical_rows_are_reversed(self):
        hall = CinemaHall.objects.create(
           name="Reversed",
            layout=(
                "GB gold oo\n"
                "gap\n"
                "GA gold oo\n"
                "gap\n"
                "B silver oo\n"
                "gap\n"
                "A silver oo\n"
            ),
        )
        show = Show.objects.create(
            movie=self.movie,
            hall=hall,
            show_date=self.today,
            start_time=time(5, 0),
        )
        generate_seats(show)

        response = self.client.get(
            reverse("seat_selection", args=[show.id])
        )

        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(
            [(row["is_gap"], row.get("label")) for row in rows],
            [
                (False, "GA"),
                (True, ""),
                (False, "GB"),
                (True, ""),
                (False, "A"),
                (True, ""),
                (False, "B"),
            ],
        )


    def test_admin_validation_message(self):
        from django.core.exceptions import ValidationError
        hall = CinemaHall(name="Bad", layout="A silver ooxo")
        with self.assertRaises(ValidationError):
            hall.full_clean()


class TicketCodeAndWordsTests(CinemaTestBase):

    def test_each_ticket_gets_a_unique_12_char_code(self):
        self.sell(["A1", "A2", "GA1", "GA2"])
        codes = list(Ticket.objects.values_list("code", flat=True))
        self.assertEqual(len(set(codes)), 4)
        for code in codes:
            self.assertRegex(code, r"^[A-HJ-NP-Z2-9]{12}$")      # no 0/O/1/I

    def test_amount_in_words_matches_sample(self):
        self.assertEqual(amount_in_words(D("300")), "Three Hundred Rupees Only")
        self.assertEqual(amount_in_words(D("400.00")), "Four Hundred Rupees Only")
        self.assertEqual(amount_in_words(D("300.50")), "Three Hundred Rupees and Fifty Paisa Only")


# --------------------------------------------------------------------------
# Reprints, QR-only, load_layout command
# --------------------------------------------------------------------------

import ast
from io import StringIO

from django.core.management import CommandError, call_command


class ReprintAndQrTests(CinemaTestBase):

    def test_first_print_is_original_later_prints_are_copies(self):
        r = self.client.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id, self.seat("A2").id]},
        )
        sale_url = r.url

        first = self.client.get(sale_url).content.decode()
        self.assertNotIn("COPY OF ORIGINAL", first)

        second = self.client.get(sale_url).content.decode()
        self.assertEqual(second.count("COPY OF ORIGINAL (1)"), 2)   # both slips

        b = Booking.objects.order_by("id").first()
        third = self.client.get(reverse("ticket_print", args=[b.id])).content.decode()
        self.assertEqual(third.count("COPY OF ORIGINAL (2)"), 1)    # only that invoice
        self.assertEqual(Booking.objects.get(id=b.id).print_count, 3)

    def test_cancelled_invoice_is_not_a_copy_and_not_counted(self):
        self.sell(["A1"])
        b = Booking.objects.get()
        self.client.get(reverse("ticket_print", args=[b.id]))
        self.client.post(reverse("booking_cancel", args=[b.id]))
        before = Booking.objects.get().print_count
        html = self.client.get(reverse("ticket_print", args=[b.id])).content.decode()
        self.assertIn("CANCELLED", html)
        self.assertNotIn("COPY OF ORIGINAL", html)
        self.assertEqual(Booking.objects.get().print_count, before)

    def test_ticket_code_is_a_standard_qr_not_micro_qr(self):
        import segno
        from .utils import ticket_code_svg
        svg = str(ticket_code_svg("ABCDEFGH2345"))
        self.assertTrue(svg.startswith("<svg"))
        qr = segno.make_qr("ABCDEFGH2345", error="m")
        self.assertFalse(qr.is_micro)

    def test_no_barcode_code_left_in_the_module(self):
        from pathlib import Path
        base = Path(__file__).parent
        for path in list(base.glob("*.py")) + list(base.glob("templates/cinema/*.html")):
            if path.name == "tests.py":
                continue
            text = path.read_text(encoding="utf-8").lower()
            self.assertNotIn("code128", text, path.name)
            self.assertNotIn("import barcode", text, path.name)


class LoadLayoutCommandTests(TestCase):

    def run_cmd(self, *args):
        out = StringIO()
        call_command("load_layout", *args, stdout=out)
        return out.getvalue()

    def test_creates_then_updates_the_hall(self):
        path = str(Path(__file__).parent / "layouts" / "audi1.txt")
        self.assertIn("Created hall 'Audi 1' with 258 seats", self.run_cmd("Audi 1", path))
        self.assertIn("Updated hall 'Audi 1'", self.run_cmd("Audi 1", path))
        self.assertEqual(CinemaHall.objects.filter(name="Audi 1").count(), 1)

    def test_bad_file_or_layout_is_a_clear_error(self):
        with self.assertRaises(CommandError):
            self.run_cmd("X", "/no/such/file.txt")
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("A bronze ooo")
        with self.assertRaises(CommandError):
            self.run_cmd("X", f.name)
        self.assertFalse(CinemaHall.objects.filter(name="X").exists())



# --------------------------------------------------------------------------
# Seat states: sold / reserved / unavailable / available (as in Khalti)
# --------------------------------------------------------------------------

from datetime import timedelta as _td

from django.test import Client


class SeatStateTests(CinemaTestBase):

    def setUp(self):
        super().setUp()
        self.staff2 = User.objects.create_user("counter2", password="pw", is_staff=True)
        self.client2 = Client()
        self.client2.force_login(self.staff2)

    def hold(self, numbers, client=None):
        return (client or self.client).get(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat(n).id for n in numbers]},
        )

    def states(self, client):
        r = client.get(reverse("seat_status", args=[self.show.id]))
        self.assertEqual(r.status_code, 200)
        return r.json()["seats"]

    # ---- reserved ----
    def test_billing_page_reserves_the_seats_for_that_counter(self):
        r = self.hold(["A1", "GA1"])
        self.assertEqual(r.status_code, 200)

        seat = self.seat("A1")
        self.assertEqual(seat.held_by, self.staff)
        left = (seat.held_until - timezone.now()).total_seconds()
        self.assertTrue(415 <= left <= 421, left)             # 7 minutes
        self.assertTrue(415 <= r.context["hold_seconds"] <= 421)
        self.assertIn("Time left", r.content.decode())

        # Other counter sees Reserved; the holder sees Available.
        other = self.states(self.client2)
        self.assertEqual(other[str(seat.id)], "reserved")
        self.assertEqual(other[str(self.seat("GA1").id)], "reserved")
        self.assertEqual(self.states(self.client)[str(seat.id)], "available")

        page = self.client2.get(reverse("seat_selection", args=[self.show.id]))
        cell = next(c for row in page.context["rows"] if not row["is_gap"]
                    for c in row["cells"] if c and c.seat_number == "A1")
        self.assertEqual(cell.state, "reserved")
        html = page.content.decode()
        self.assertIn('data-state="reserved"', html)
        for word in ("Reserved", "Sold", "Unavailable", "Selected"):
            self.assertIn(word, html)

    def test_other_counter_cannot_bill_or_sell_reserved_seats(self):
        self.hold(["A1"])

        r = self.client2.get(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id]}, follow=True,
        )
        self.assertEqual(r.redirect_chain[-1][0], reverse("seat_selection", args=[self.show.id]))
        self.assertTrue(any("Reserved by another counter: A1" in m for m in self.messages(r)))

        r = self.client2.post(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A1").id]},
        )
        self.assertEqual(Booking.objects.count(), 0)
        self.assertFalse(self.seat("A1").is_booked)

        # direct hit on the locked sale logic too
        req = RequestFactory().post("/", {"seats": [self.seat("A1").id]})
        req.user = self.staff2
        with self.assertRaises(BookingError) as cm:
            with transaction.atomic():
                _create_sale(req, self.show)
        self.assertIn("Reserved by another counter", str(cm.exception))

    def test_refreshing_billing_does_not_extend_the_hold(self):
        self.hold(["A1"])
        early = timezone.now() + _td(seconds=60)
        Seat.objects.filter(id=self.seat("A1").id).update(held_until=early)

        r = self.hold(["A1"])
        self.assertEqual(self.seat("A1").held_until, early)
        self.assertTrue(55 <= r.context["hold_seconds"] <= 61)

    def test_expired_hold_frees_the_seat(self):
        self.hold(["A1"])
        Seat.objects.filter(id=self.seat("A1").id).update(
            held_until=timezone.now() - _td(seconds=1)
        )
        self.assertEqual(self.states(self.client2)[str(self.seat("A1").id)], "available")
        r = self.hold(["A1"], client=self.client2)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.seat("A1").held_by, self.staff2)

    def test_holder_can_sell_and_hold_is_cleared(self):
        self.hold(["A1", "GA1"])
        self.sell(["A1", "GA1"])
        self.assertEqual(Booking.objects.count(), 2)
        for n in ("A1", "GA1"):
            s = self.seat(n)
            self.assertTrue(s.is_booked)
            self.assertIsNone(s.held_by)
            self.assertIsNone(s.held_until)
        self.assertEqual(self.states(self.client2)[str(self.seat("A1").id)], "sold")

    def test_cancel_returns_seat_to_available_for_everyone(self):
        self.sell(["A1"])
        self.client.post(reverse("booking_cancel", args=[Booking.objects.get().id]))
        self.assertEqual(self.states(self.client2)[str(self.seat("A1").id)], "available")

    @override_settings(CINEMA_HOLD_MINUTES=2)
    def test_hold_time_is_configurable(self):
        r = self.hold(["A1"])
        self.assertTrue(115 <= r.context["hold_seconds"] <= 121)

    # ---- unavailable ----
    def test_blocked_seat_is_unavailable_everywhere(self):
        Seat.objects.filter(id=self.seat("A2").id).update(is_blocked=True)
        sid = str(self.seat("A2").id)

        for c in (self.client, self.client2):
            self.assertEqual(self.states(c)[sid], "unavailable")

        r = self.client.get(
            reverse("ticket_checkout", args=[self.show.id]),
            {"seats": [self.seat("A2").id]}, follow=True,
        )
        self.assertTrue(any("Unavailable: A2" in m for m in self.messages(r)))

        self.sell(["A2"])
        self.assertEqual(Booking.objects.count(), 0)

        page = self.client.get(reverse("seat_selection", args=[self.show.id]))
        self.assertIn('data-state="unavailable"', page.content.decode())

    def test_admin_can_block_and_unblock_but_not_sold_seats(self):
        admin = User.objects.create_superuser("root", "r@x.com", "pw")
        c = Client(); c.force_login(admin)
        url = reverse("admin:cinema_seat_changelist")

        self.sell(["A1"])                               # sold
        ids = [self.seat("A1").id, self.seat("A2").id, self.seat("A3").id]

        c.post(url, {"action": "make_unavailable", "_selected_action": ids})
        self.assertTrue(self.seat("A1").is_booked)
        self.assertFalse(self.seat("A1").is_blocked)    # sold seat left alone
        self.assertTrue(self.seat("A2").is_blocked)
        self.assertTrue(self.seat("A3").is_blocked)

        c.post(url, {"action": "make_available", "_selected_action": ids})
        self.assertFalse(self.seat("A2").is_blocked)

    # ---- status endpoint ----
    def test_status_endpoint(self):
        self.sell(["B1"])
        data = self.client.get(reverse("seat_status", args=[self.show.id])).json()
        self.assertEqual(data["total"], 25)
        self.assertEqual(data["sold"], 1)
        self.assertEqual(data["seats"][str(self.seat("B1").id)], "sold")
        self.assertEqual(set(data["seats"].values()), {"sold", "available"})

    def test_status_endpoint_is_staff_only(self):
        self.client.force_login(self.cashier)
        self.assertEqual(
            self.client.get(reverse("seat_status", args=[self.show.id])).status_code, 403
        )

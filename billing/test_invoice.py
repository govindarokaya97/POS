"""Invoice page, receipt layouts, PDFs and the amount-in-words helper."""
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import Customer, Invoice, InvoiceItem, ShopSetting
from billing.utils import amount_in_words
from inventory.models import Category, Product


class AmountInWordsTests(TestCase):
    def test_examples(self):
        cases = {
            "0": "Rupees Zero Only",
            "113": "Rupees One Hundred Thirteen Only",
            "113.50": "Rupees One Hundred Thirteen and Fifty Paisa Only",
            "100000": "Rupees One Lakh Only",
            "1234567.50": "Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Fifty Paisa Only",
            "10000000": "Rupees One Crore Only",
            "0.07": "Seven Paisa Only",
        }
        for value, words in cases.items():
            self.assertEqual(amount_in_words(Decimal(value)), words, value)


class InvoiceBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cashier = User.objects.create_user("cashier", password="pw12345!", first_name="Sita", last_name="Gurung")
        cls.owner = User.objects.create_user("owner", password="pw12345!", is_staff=True)
        cls.shop = ShopSetting.objects.create(
            shop_name="Himalayan Trading Pvt. Ltd.", vat_number="601234567",
            address="Lakeside-6, Pokhara", phone="061-123456", email="sales@himalayan.example",
            footer_message="Thank you for shopping with us!",
        )
        cat = Category.objects.create(name="Grocery")
        cls.rice = Product.objects.create(category=cat, name="Rice & <Beans> 25kg", price=Decimal("3450.00"), stock=50)
        cls.customer = Customer.objects.create(name="Ram Thapa", phone="9841000000", address="Ward 8, Pokhara")

        # 2 x 3450 = 6900; discount 400 -> taxable 6500; VAT 13% = 845; total 7345
        cls.invoice = Invoice.objects.create(
            invoice_number="INV-00001", customer=cls.customer, created_by=cls.cashier,
            subtotal=Decimal("6900.00"), discount=Decimal("400.00"), vat=Decimal("845.00"),
            vat_percent=Decimal("13.00"), total=Decimal("7345.00"), paid_amount=Decimal("5000.00"),
            due_amount=Decimal("2345.00"), payment_status="partial", payment_method="esewa",
        )
        InvoiceItem.objects.create(invoice=cls.invoice, product=cls.rice, quantity=2,
                                   price=Decimal("3450.00"), total=Decimal("6900.00"))

    def setUp(self):
        self.client.login(username="cashier", password="pw12345!")

    def page(self, qs=""):
        r = self.client.get(reverse("invoice", args=[self.invoice.id]) + qs)
        self.assertEqual(r.status_code, 200)
        return r.content.decode()


class InvoicePageTests(InvoiceBase):
    def test_company_name_is_followed_by_vat_number(self):
        html = self.page()
        name_at = html.index("Himalayan Trading Pvt. Ltd.", html.index('class="company'))
        vat_at = html.index("VAT No.", name_at)
        self.assertIn("601234567", html[vat_at:vat_at + 80])
        self.assertLess(vat_at - name_at, 120)

    def test_is_a_tax_invoice_when_vat_number_is_set(self):
        self.assertIn("Tax Invoice", self.page())

    def test_plain_invoice_without_vat_number(self):
        ShopSetting.objects.update(vat_number="")
        html = self.page()
        self.assertNotIn("Tax Invoice", html)
        self.assertNotIn("VAT No.", html)
        self.assertIn("VAT number", html)  # reminder notice for the owner

    def test_shows_vat_rate_amounts_and_balance(self):
        html = self.page()
        self.assertIn("VAT (13%)", html)
        self.assertIn("Rs 845.00", html)          # VAT amount
        self.assertIn("Rs 6,500.00", html)        # taxable amount
        self.assertIn("Rs 7,345.00", html)        # total
        self.assertIn("Balance due", html)
        self.assertIn("Rupees Seven Thousand Three Hundred Forty Five Only", html)

    def test_escapes_product_names(self):
        html = self.page()
        self.assertIn("Rice &amp; &lt;Beans&gt; 25kg", html)

    def test_default_layout_is_a4_and_receipts_are_selectable(self):
        self.assertIn('class="sheet"', self.page())
        r58 = self.page("?layout=receipt&paper=58")
        r80 = self.page("?layout=receipt&paper=80")
        self.assertIn("receipt p58", r58)
        self.assertIn("receipt p80", r80)
        self.assertIn("VAT No.: 601234567", r58)
        self.assertIn('class="sheet"', self.page("?layout=bogus"))

    def test_page_works_without_any_shop_settings(self):
        ShopSetting.objects.all().delete()
        html = self.page()
        self.assertIn("Company name not set", html)
        self.assertIn("company name and VAT number", html)

    def test_legacy_invoice_derives_vat_percent(self):
        legacy = Invoice.objects.create(
            invoice_number="INV-OLD", created_by=self.cashier, subtotal=Decimal("100.00"),
            vat=Decimal("13.00"), total=Decimal("113.00"), vat_percent=None,
        )
        self.assertEqual(legacy.vat_percent_display, Decimal("13.00"))

    def test_login_required(self):
        self.client.logout()
        r = self.client.get(reverse("invoice", args=[self.invoice.id]))
        self.assertEqual(r.status_code, 302)


class InvoiceSavedRateTests(InvoiceBase):
    def test_checkout_saves_the_vat_percent_used(self):
        s = self.client.session
        s["cart"] = {str(self.rice.id): {"quantity": 1, "price": "3450.00"}}
        s.save()
        self.client.post(reverse("checkout"), {
            "payment_method": "cash", "paid_amount": "0", "discount": "0", "vat": "15.5",
        })
        inv = Invoice.objects.order_by("-id").first()
        self.assertEqual(inv.vat_percent, Decimal("15.50"))
        self.assertEqual(inv.vat_percent_display, Decimal("15.50"))


class InvoicePdfTests(InvoiceBase):
    def pdf(self, qs=""):
        r = self.client.get(reverse("invoice_pdf", args=[self.invoice.id]) + qs)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        return r.content

    @staticmethod
    def pages(content):
        return len(re.findall(rb"/Type /Page\b", content))

    def test_all_layouts_build(self):
        self.assertEqual(self.pages(self.pdf()), 1)
        self.assertEqual(self.pages(self.pdf("?layout=receipt&paper=58")), 1)
        self.assertEqual(self.pages(self.pdf("?layout=receipt&paper=80")), 1)

    def test_long_receipt_still_fits_one_page(self):
        cat = Category.objects.first()
        for i in range(60):
            p = Product.objects.create(category=cat, name=f"Item {i} with a fairly long description text",
                                       price=Decimal("10.00"), stock=5)
            InvoiceItem.objects.create(invoice=self.invoice, product=p, quantity=1,
                                       price=Decimal("10.00"), total=Decimal("10.00"))
        self.assertEqual(self.pages(self.pdf("?layout=receipt&paper=58")), 1)
        self.assertGreater(self.pages(self.pdf()), 1)

    def test_pdf_without_shop_settings_does_not_crash(self):
        ShopSetting.objects.all().delete()
        self.pdf()
        self.pdf("?layout=receipt")

    @staticmethod
    def text(content):
        with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
            f.write(content)
            f.flush()
            return subprocess.check_output(["pdftotext", "-layout", f.name, "-"]).decode()

    def test_pdf_text_has_company_then_vat_number(self):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext not installed")
        for qs in ("", "?layout=receipt&paper=58"):
            text = self.text(self.pdf(qs))
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            i = next(n for n, l in enumerate(lines) if l.startswith("Himalayan Trading"))
            self.assertTrue("VAT No.: 601234567" in lines[i + 1] or "VAT No.: 601234567" in lines[i + 2], qs)
            self.assertIn("VAT (13%)", text)
            self.assertIn("Rice & <Beans> 25kg", text)
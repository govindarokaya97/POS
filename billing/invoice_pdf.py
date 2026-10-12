"""PDF versions of an invoice: an A4 tax invoice and a 58/80 mm receipt.

Both are built from the context made by views._invoice_context().
"""
import os
from decimal import Decimal
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#12141A")
BRAND = colors.HexColor("#157A5C")
LINE = colors.HexColor("#E4E3DC")
PAPER = colors.HexColor("#F4F5F1")
MUTED = colors.HexColor("#6B6D66")
AMBER = colors.HexColor("#C97A1F")


def _m(value):
    return f"{Decimal(value):,.2f}"


def _esc(text):
    """Paragraph() reads markup, so product/customer text must be escaped."""
    return escape(str(text or ""))


def _multiline(text):
    return _esc(text).replace("\r\n", "\n").replace("\n", "<br/>")


def _style(name, **kw):
    kw.setdefault("fontName", "Helvetica")
    kw.setdefault("textColor", INK)
    return ParagraphStyle(name, **kw)


def _company_name(shop):
    return shop.shop_name if shop and shop.shop_name else "Company name not set"


def _logo(shop, max_height):
    try:
        if shop and shop.logo and os.path.exists(shop.logo.path):
            img = Image(shop.logo.path)
            scale = max_height / float(img.imageHeight)
            img.drawHeight = max_height
            img.drawWidth = img.imageWidth * scale
            img.hAlign = "LEFT"
            return img
    except Exception:
        pass
    return None


def _title(ctx):
    return "TAX INVOICE" if ctx["is_tax_invoice"] else "INVOICE"


def _customer_lines(invoice):
    c = invoice.customer
    if not c:
        return ["Walk-in customer"]
    lines = [c.name]
    for part in (c.address, c.phone, c.email):
        if part:
            lines.append(part)
    return lines


def _local_date(invoice):
    return timezone.localtime(invoice.created_at).strftime("%d %b %Y, %I:%M %p")


# ----------------------------------------------------------------------
# A4
# ----------------------------------------------------------------------

def _a4(response, ctx):
    invoice, shop = ctx["invoice"], ctx["shop"]

    margin = 18 * mm
    W = A4[0] - 2 * margin

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{_title(ctx).title()} {invoice.invoice_number}",
        author=_company_name(shop),
    )

    company = _style("company", fontName="Helvetica-Bold", fontSize=17, leading=21)
    vatno = _style("vatno", fontSize=10, leading=14)
    small = _style("small", fontSize=8.5, leading=12, textColor=MUTED)
    doc_title = _style("doctitle", fontName="Helvetica-Bold", fontSize=20, leading=24,
                       textColor=BRAND, alignment=TA_RIGHT)
    meta = _style("meta", fontSize=9, leading=13.5, alignment=TA_RIGHT)
    label = _style("label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=MUTED)
    body = _style("body", fontSize=9.5, leading=13.5)
    bold = _style("bold", fontName="Helvetica-Bold", fontSize=9.5, leading=13.5)
    cell = _style("cell", fontSize=9, leading=12)

    story = []

    # ---- header: company (name, VAT no. directly below) | invoice details
    left = []
    logo = _logo(shop, 14 * mm)
    if logo:
        left += [logo, Spacer(1, 4)]
    left.append(Paragraph(_esc(_company_name(shop)), company))
    if shop and shop.vat_number:
        left.append(Paragraph(f"VAT No.: <b>{_esc(shop.vat_number)}</b>", vatno))
    left.append(Spacer(1, 3))
    if shop and shop.address:
        left.append(Paragraph(_multiline(shop.address), small))
    contact = "  |  ".join(
        part for part in (
            f"Tel: {shop.phone}" if shop and shop.phone else "",
            shop.email if shop and shop.email else "",
        ) if part
    )
    if contact:
        left.append(Paragraph(_esc(contact), small))

    status = invoice.payment_status.title()
    right = [
        Paragraph(_title(ctx), doc_title),
        Spacer(1, 6),
        Paragraph(f"Invoice no.&nbsp;&nbsp;<b>{_esc(invoice.invoice_number)}</b>", meta),
        Paragraph(f"Date&nbsp;&nbsp;<b>{_esc(_local_date(invoice))}</b>", meta),
        Paragraph(f"Payment&nbsp;&nbsp;<b>{_esc(ctx['payment_method_label'])}</b>", meta),
        Paragraph(f"Status&nbsp;&nbsp;<b>{_esc(status)}</b>", meta),
    ]

    header = Table([[left, right]], colWidths=[W * 0.58, W * 0.42])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [header, HRFlowable(width="100%", thickness=1.4, color=BRAND,
                                 spaceBefore=10, spaceAfter=12)]

    # ---- bill to / served by
    cust = _customer_lines(invoice)
    bill = [Paragraph("Bill to", label), Spacer(1, 2), Paragraph(_esc(cust[0]), bold)]
    bill += [Paragraph(_multiline(x), body) for x in cust[1:]]
    served = [Paragraph("Served by", label), Spacer(1, 2),
              Paragraph(_esc(ctx["served_by"]), body)]

    parties = Table([[bill, served]], colWidths=[W * 0.58, W * 0.42])
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [parties, Spacer(1, 14)]

    # ---- items
    rows = [["#", "Description", "Qty", "Rate (Rs)", "Amount (Rs)"]]
    for n, item in enumerate(ctx["items"], start=1):
        rows.append([
            str(n),
            Paragraph(_esc(item.product.name), cell),
            str(item.quantity),
            _m(item.price),
            _m(item.total),
        ])

    widths = [10 * mm, W - 10 * mm - 16 * mm - 30 * mm - 34 * mm,
              16 * mm, 30 * mm, 34 * mm]
    items = Table(rows, colWidths=widths, repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, LINE),
    ]))
    story += [items, Spacer(1, 12)]

    # ---- totals
    lines = [("Subtotal", f"Rs {_m(invoice.subtotal)}")]
    if invoice.discount > 0:
        lines.append(("Discount", f"- Rs {_m(invoice.discount)}"))
        lines.append(("Taxable amount", f"Rs {_m(ctx['taxable'])}"))
    lines.append((f"VAT ({ctx['vat_percent'].normalize():f}%)", f"Rs {_m(invoice.vat)}"))
    lines.append(("Total", f"Rs {_m(invoice.total)}"))
    total_row = len(lines) - 1
    lines.append(("Paid", f"Rs {_m(invoice.paid_amount)}"))
    if ctx["return_amount"] > 0:
        lines.append(("Change returned", f"Rs {_m(ctx['return_amount'])}"))
    due_row = None
    if invoice.due_amount > 0:
        lines.append(("Balance due", f"Rs {_m(invoice.due_amount)}"))
        due_row = len(lines) - 1

    tw = 82 * mm
    totals = Table(lines, colWidths=[tw * 0.5, tw * 0.5])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, total_row), (-1, total_row), PAPER),
        ("LINEABOVE", (0, total_row), (-1, total_row), 1.2, BRAND),
        ("FONTNAME", (0, total_row), (-1, total_row), "Helvetica-Bold"),
        ("FONTSIZE", (0, total_row), (-1, total_row), 11.5),
        ("TOPPADDING", (0, total_row), (-1, total_row), 7),
        ("BOTTOMPADDING", (0, total_row), (-1, total_row), 7),
    ]
    if due_row is not None:
        style += [("TEXTCOLOR", (0, due_row), (-1, due_row), AMBER),
                  ("FONTNAME", (0, due_row), (-1, due_row), "Helvetica-Bold")]
    totals.setStyle(TableStyle(style))

    totals_row = Table([["", totals]], colWidths=[W - tw, tw])
    totals_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    words = Paragraph(f"<b>Amount in words:</b> {_esc(ctx['amount_in_words'])}", body)

    sign = Table(
        [["", "", ""], ["Customer signature", "", "Authorized signature"]],
        colWidths=[W * 0.36, W * 0.28, W * 0.36],
        rowHeights=[26 * mm * 0.8, None],
    )
    sign.setStyle(TableStyle([
        ("LINEABOVE", (0, 1), (0, 1), 0.6, MUTED),
        ("LINEABOVE", (2, 1), (2, 1), 0.6, MUTED),
        ("FONTSIZE", (0, 1), (-1, 1), 8),
        ("TEXTCOLOR", (0, 1), (-1, 1), MUTED),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))

    footer_msg = (shop.footer_message if shop and shop.footer_message
                  else "Thank you for your business.")
    thanks = Paragraph(_multiline(footer_msg),
                       _style("thanks", fontSize=9, leading=13, alignment=TA_CENTER, textColor=MUTED))

    story.append(KeepTogether([totals_row, Spacer(1, 10), words]))
    story.append(KeepTogether([Spacer(1, 6), sign, Spacer(1, 14), thanks]))

    def page_footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, 10 * mm, invoice.invoice_number)
        canvas.drawRightString(A4[0] - margin, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


# ----------------------------------------------------------------------
# Thermal receipt (58 mm or 80 mm roll)
# ----------------------------------------------------------------------

def _receipt(response, ctx, paper):
    invoice, shop = ctx["invoice"], ctx["shop"]

    page_w = (80 if paper == "80" else 58) * mm
    margin = (3 if paper == "80" else 5) * mm
    avail = page_w - 2 * margin

    center = _style("c", fontSize=8, leading=10.5, alignment=TA_CENTER)
    name = _style("n", fontName="Helvetica-Bold", fontSize=11, leading=13.5, alignment=TA_CENTER)
    vat = _style("v", fontName="Helvetica-Bold", fontSize=8.5, leading=11, alignment=TA_CENTER)
    muted = _style("m", fontSize=7.5, leading=10, alignment=TA_CENTER, textColor=MUTED)
    title = _style("t", fontName="Helvetica-Bold", fontSize=9.5, leading=12, alignment=TA_CENTER)
    cell = _style("cell", fontSize=8, leading=10)

    def dashed():
        return HRFlowable(width="100%", thickness=0.6, color=INK, dash=[2, 2],
                          spaceBefore=4, spaceAfter=4)

    story = []

    logo = _logo(shop, 12 * mm)
    if logo:
        logo.hAlign = "CENTER"
        story += [logo, Spacer(1, 3)]
    story.append(Paragraph(_esc(_company_name(shop)), name))
    if shop and shop.vat_number:
        story.append(Paragraph(f"VAT No.: {_esc(shop.vat_number)}", vat))
    if shop and shop.address:
        story.append(Paragraph(_multiline(shop.address), muted))
    if shop and shop.phone:
        story.append(Paragraph(f"Tel: {_esc(shop.phone)}", muted))
    story.append(dashed())
    story.append(Paragraph(_title(ctx), title))
    story.append(Spacer(1, 3))

    info = Table([
        ["Invoice", invoice.invoice_number],
        ["Date", _local_date(invoice)],
        ["Customer", Paragraph(_esc(_customer_lines(invoice)[0]), cell)],
        ["Payment", ctx["payment_method_label"]],
    ], colWidths=[avail * 0.34, avail * 0.66])
    info.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [info, dashed()]

    rows, spans = [], []
    for item in ctx["items"]:
        r = len(rows)
        rows.append([Paragraph(_esc(item.product.name), cell), ""])
        rows.append([f"{item.quantity} x {_m(item.price)}", _m(item.total)])
        spans.append(("SPAN", (0, r), (1, r)))
    items = Table(rows, colWidths=[avail * 0.62, avail * 0.38])
    items.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ] + spans))
    story += [items, dashed()]

    lines = [("Subtotal", _m(invoice.subtotal))]
    if invoice.discount > 0:
        lines.append(("Discount", "-" + _m(invoice.discount)))
        lines.append(("Taxable", _m(ctx["taxable"])))
    lines.append((f"VAT ({ctx['vat_percent'].normalize():f}%)", _m(invoice.vat)))
    lines.append(("TOTAL (Rs)", _m(invoice.total)))
    total_row = len(lines) - 1
    lines.append(("Paid", _m(invoice.paid_amount)))
    if ctx["return_amount"] > 0:
        lines.append(("Change", _m(ctx["return_amount"])))
    if invoice.due_amount > 0:
        lines.append(("Balance due", _m(invoice.due_amount)))

    totals = Table(lines, colWidths=[avail * 0.55, avail * 0.45])
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
        ("FONTNAME", (0, total_row), (-1, total_row), "Helvetica-Bold"),
        ("FONTSIZE", (0, total_row), (-1, total_row), 10.5),
        ("LINEABOVE", (0, total_row), (-1, total_row), 0.6, INK),
        ("TOPPADDING", (0, total_row), (-1, total_row), 4),
        ("BOTTOMPADDING", (0, total_row), (-1, total_row), 4),
    ]))
    story += [totals, dashed()]

    story.append(Paragraph(_esc(ctx["amount_in_words"]), muted))
    story.append(Spacer(1, 4))
    footer_msg = (shop.footer_message if shop and shop.footer_message
                  else "Thank you for your business.")
    story.append(Paragraph(_multiline(footer_msg), center))

    # Roll paper has no fixed length: measure the content and size the page to it.
    content_h = 0
    for flowable in story:
        _, h = flowable.wrap(avail, 10000 * mm)
        content_h += h + flowable.getSpaceBefore() + flowable.getSpaceAfter()
    page_h = content_h + 2 * margin + 8 * mm

    # SimpleDocTemplate's frame adds 6 pt of padding on every side, so pull
    # the margins in by that much to keep the text width equal to `avail`.
    inset = margin - 6

    doc = SimpleDocTemplate(
        response,
        pagesize=(page_w, page_h),
        leftMargin=inset, rightMargin=inset,
        topMargin=inset, bottomMargin=inset,
        title=f"Receipt {invoice.invoice_number}",
        author=_company_name(shop),
    )
    doc.build(story)


def build_invoice_pdf(response, ctx, layout="a4", paper="58"):
    if layout == "receipt":
        _receipt(response, ctx, paper)
    else:
        _a4(response, ctx)
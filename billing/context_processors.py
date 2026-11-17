from .models import Invoice
from inventory.models import Product
from django.core.cache import cache


def sidebar_notifications(request):
    if not request.user.is_authenticated:
        return {}

    def load_notifications():
        low_stock = Product.objects.filter(stock__lte=5)
        pending = Invoice.objects.filter(due_amount__gt=0)
        return {
            "low_stock_products": list(
                low_stock.order_by("stock").values("id", "name", "stock")[:5]
            ),
            "pending_invoices": list(
                pending.order_by("-created_at").values(
                    "id", "invoice_number", "due_amount", "created_at"
                )[:5]
            ),
            "low_stock_count": low_stock.count(),
            "pending_payment_count": pending.count(),
        }

    return cache.get_or_set("sidebar_notifications", load_notifications, 30)

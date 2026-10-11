from .models import Invoice
from inventory.models import Product


def sidebar_notifications(request):

    if not request.user.is_authenticated:
        return {}


    low_stock_products = Product.objects.filter(
        stock__lte=5
    ).order_by(
        "stock"
    )[:5]


    pending_invoices = Invoice.objects.filter(
        due_amount__gt=0
    ).order_by(
        "-created_at"
    )[:5]


    return {

        "low_stock_products": low_stock_products,

        "pending_invoices": pending_invoices,


        "low_stock_count":
            Product.objects.filter(
                stock__lte=5
            ).count(),


        "pending_payment_count":
            Invoice.objects.filter(
                due_amount__gt=0
            ).count(),

    }
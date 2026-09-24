from django.contrib import admin
from .models import Customer,Invoice,InvoiceItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "phone",
        "email",
        "created_at",
    )

admin.site.register(Invoice)

admin.site.register(InvoiceItem)
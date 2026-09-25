from django.contrib import admin
from .models import Customer,Invoice,InvoiceItem, Expense


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


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "expense_type",
        "amount",
        "created_at",
    )
from django.contrib import admin
from .models import Sale
# Register your models here.

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('product', 'sold_by', 'quantity', 'total_price', 'sold_by', 'sold_at')
    list_filter = ('sold_by', 'sold_at')
    search_fields = ('product__name', 'sold_by__username')
    ordering = ('-sold_at',)
    list_per_page = 20
from django import forms
from .models import ShopSetting


class ShopSettingForm(forms.ModelForm):
    class Meta:
        model = ShopSetting
        fields = [
            "shop_name",
            "address",
            "phone",
            "email",
            "vat_number",
            "logo",
            "footer_message",
        ]

        widgets = {
            "shop_name": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "placeholder": "Enter shop or business name",
            }),
            "address": forms.Textarea(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "rows": 3,
                "placeholder": "Enter business address",
            }),
            "phone": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "placeholder": "Phone number",
            }),
            "email": forms.EmailInput(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "placeholder": "Business email",
            }),
            "vat_number": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "placeholder": "VAT / PAN number",
            }),
            "logo": forms.ClearableFileInput(attrs={
                "class": "block w-full text-sm text-muted file:mr-4 file:rounded-lg file:border-0 file:bg-brand/10 file:px-4 file:py-2 file:font-semibold file:text-brand",
            }),
            "footer_message": forms.TextInput(attrs={
                "class": "w-full rounded-xl border border-line bg-white px-4 py-3 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15",
                "placeholder": "Thank You! Visit Again",
            }),
        }

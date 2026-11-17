
import re

from django import forms
from django.contrib.auth.forms import (
    UserCreationForm,
    AuthenticationForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


INPUT_CLASSES = (
    "w-full rounded-lg border border-line bg-paper px-4 py-3 "
    "text-sm text-ink outline-none transition "
    "focus:border-brand focus:ring-2 focus:ring-brand/20"
)


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        max_length=254,
        required=True,
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Username",
            "autocomplete": "username",
        }),
    )

    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Password",
            "autocomplete": "current-password",
        }),
    )


class RegisterForm(UserCreationForm):

    full_name = forms.CharField(
        max_length=150,
        required=True,
        label="Full Name",
        widget=forms.TextInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Enter your full name",
            "autocomplete": "name",
        }),
    )

    email = forms.EmailField(
        required=True,
        label="Email Address",
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Enter your email address",
            "autocomplete": "email",
        }),
    )

    mobile_number = forms.CharField(
        max_length=20,
        required=True,
        label="Mobile Number",
        widget=forms.TelInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "98XXXXXXXX",
            "autocomplete": "tel",
            "inputmode": "tel",
        }),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": INPUT_CLASSES,
            "placeholder": "Choose a username",
            "autocomplete": "username",
        })

        self.fields["password1"].widget.attrs.update({
            "class": INPUT_CLASSES,
            "placeholder": "Create a password",
            "autocomplete": "new-password",
        })

        self.fields["password2"].widget.attrs.update({
            "class": INPUT_CLASSES,
            "placeholder": "Confirm your password",
            "autocomplete": "new-password",
        })

        self.order_fields([
            "full_name",
            "username",
            "email",
            "mobile_number",
            "password1",
            "password2",
        ])

    def clean_full_name(self):
        full_name = self.cleaned_data["full_name"].strip()

        if len(full_name.split()) < 2:
            raise ValidationError(
                "Please enter your first and last name."
            )

        return full_name

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email address already exists."
            )

        return email

    def clean_mobile_number(self):
        mobile = self.cleaned_data["mobile_number"].strip()

        # Remove common formatting characters.
        mobile = re.sub(r"[\s()-]", "", mobile)

        # Accept Nepal country code.
        if mobile.startswith("+977"):
            mobile = mobile[4:]
        elif mobile.startswith("977"):
            mobile = mobile[3:]

        # Nepal mobile numbers: 10 digits, beginning with 96, 97 or 98.
        if not re.fullmatch(r"9[678]\d{8}", mobile):
            raise ValidationError(
                "Enter a valid Nepal mobile number, "
                "for example 98XXXXXXXX."
            )

        # Normalized local number. It is validated but not stored.
        return mobile

    def save(self, commit=True):
        user = super().save(commit=False)

        full_name = self.cleaned_data["full_name"].strip()
        name_parts = full_name.split(maxsplit=1)

        user.first_name = name_parts[0]
        user.last_name = name_parts[1] if len(name_parts) > 1 else ""
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()
            self.save_m2m()

        return user

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
        )



class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name")

        widgets = {
            "username": forms.TextInput(attrs={
                "class": INPUT_CLASSES,
                "autocomplete": "username",
            }),
            "first_name": forms.TextInput(attrs={
                "class": INPUT_CLASSES,
                "autocomplete": "given-name",
            }),
            "last_name": forms.TextInput(attrs={
                "class": INPUT_CLASSES,
                "autocomplete": "family-name",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].label = "Username"
        self.fields["first_name"].label = "First name"
        self.fields["last_name"].label = "Last name"





class UserManagementForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": INPUT_CLASSES,
            "placeholder": "Enter email address",
        }),
    )

    ROLE_CHOICES = (
        ("cashier", "Cashier"),
        ("staff", "Staff"),
        ("admin", "Administrator"),
    )

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={
            "class": INPUT_CLASSES,
        }),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "password1",
            "password2",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": INPUT_CLASSES,
            })

        self.fields["username"].widget.attrs.update({
            "placeholder": "Enter username",
        })
        self.fields["first_name"].widget.attrs.update({
            "placeholder": "First name",
        })
        self.fields["last_name"].widget.attrs.update({
            "placeholder": "Last name",
        })
        self.fields["password1"].widget.attrs.update({
            "placeholder": "Create password",
        })
        self.fields["password2"].widget.attrs.update({
            "placeholder": "Confirm password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        user.email = self.cleaned_data["email"]
        user.is_active = True

        role = self.cleaned_data["role"]
        user.is_staff = role in ("staff", "admin")
        user.is_superuser = role == "admin"

        if commit:
            user.save()

        return user





class UserEditForm(forms.ModelForm):
    ROLE_CHOICES = (
        ("cashier", "Cashier"),
        ("staff", "Staff"),
        ("admin", "Administrator"),
    )

    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        widget=forms.Select(attrs={
            "class": INPUT_CLASSES,
        }),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update({
                "class": INPUT_CLASSES,
            })

        if self.instance and self.instance.pk:
            if self.instance.is_superuser:
                self.fields["role"].initial = "admin"
            elif self.instance.is_staff:
                self.fields["role"].initial = "staff"
            else:
                self.fields["role"].initial = "cashier"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        existing = User.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError(
                "Another account already uses this email."
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        role = self.cleaned_data["role"]
        user.is_staff = role in ("staff", "admin")
        user.is_superuser = role == "admin"

        if commit:
            user.save()

        return user

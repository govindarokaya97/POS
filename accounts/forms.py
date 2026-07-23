from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User



class LoginForm(AuthenticationForm):
    username = forms.CharField(
        max_length=254,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full rounded-lg border border-line bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20',
            'placeholder': 'Username'
        })
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full rounded-lg border border-line bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20',
            'placeholder': 'Password'
        })
    )

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Design-system classes for form inputs (see templates/base.html @theme)
        input_classes = "w-full rounded-lg border border-line bg-paper px-4 py-3 text-sm text-ink outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20"
        
        # Apply classes to all fields
        self.fields['username'].widget.attrs.update({
            'class': input_classes,
            'placeholder': 'Enter your username'
        })
        
        self.fields['email'].widget.attrs.update({
            'class': input_classes,
            'placeholder': 'Enter your email'
        })
        
        self.fields['password1'].widget.attrs.update({
            'class': input_classes,
            'placeholder': 'Enter your password'
        })
        
        self.fields['password2'].widget.attrs.update({
            'class': input_classes,
            'placeholder': 'Confirm your password'
        })

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]
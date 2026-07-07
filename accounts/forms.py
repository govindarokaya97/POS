from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User



class LoginForm(AuthenticationForm):
    username = forms.CharField(
        max_length=254,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:border-blue-600 transition duration-200',
            'placeholder': 'Username'
        })
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border-2 border-gray-300 rounded-lg focus:outline-none focus:border-blue-600 transition duration-200',
            'placeholder': 'Password'
        })
    )

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Tailwind CSS classes for form inputs
        input_classes = "w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500 focus:ring-opacity-50 transition duration-200"
        
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
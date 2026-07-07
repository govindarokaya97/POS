from django.shortcuts import render, redirect
from .forms import RegisterForm, LoginForm
from django.contrib import messages

# Create your views here.

def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            form.save()

            messages.success(request, "Account Created Successfully")
            return redirect("login")
            
    else:
        form = RegisterForm()
    context = {
        "form":form
    }
    return render(request, 'accounts/register.html',context)

def login(request):
    return render(request, 'accounts/login.html')

def logout(request):
    return render(request, 'accounts/logout.html')
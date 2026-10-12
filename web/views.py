from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages


def index(request):
    return render(request, 'web/index.html')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Tạo tài khoản thành công! Chào {user.username}.')
            return redirect('/ai/')
    else:
        form = UserCreationForm()
    return render(request, 'web/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    error = ''
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next', '/ai/')
            return redirect(next_url)
        else:
            error = 'Tên đăng nhập hoặc mật khẩu không đúng.'
    else:
        form = AuthenticationForm()
    return render(request, 'web/login.html', {'form': form, 'error': error})


def logout_view(request):
    logout(request)
    return redirect('/')


@login_required(login_url='/login/?next=/ai/')
def ai_judge(request):
    return render(request, 'web/ai_judge.html', {'user': request.user})


def ranking_view(request):
    return render(request, 'web/ranking.html')

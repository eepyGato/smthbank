# core/decorators.py
from django.core.exceptions import PermissionDenied
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.shortcuts import redirect
from functools import wraps


def role_required(allowed_roles):
    """Декоратор для проверки роли пользователя"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            
            if request.user.role not in allowed_roles and not request.user.is_superuser:
                raise PermissionDenied('У вас нет доступа к этой странице')
            
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def client_required(view_func):
    """Только для клиентов"""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.role != 'client':
            # Перенаправляем в зависимости от роли
            if request.user.role == 'admin':
                return redirect('core:admin_clients')
            elif request.user.role == 'manager':
                return redirect('core:manager_clients')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapped


def manager_required(view_func):
    """Только для менеджеров и админов"""
    return role_required(['manager', 'admin'])(view_func)


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != 'admin':
            return redirect('home')  # или 'core:home'
        return view_func(request, *args, **kwargs)
    return wrapped
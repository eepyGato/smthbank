# core/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.html import format_html
from .models import (
    User, ClientProfile, Asset, PortfolioItem, Transaction,
    WithdrawRequest, Company, Employee, PriceHistory, SystemLog,
    CommissionSettings
)


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User


class CustomUserAdmin(BaseUserAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    model = User
    
    list_display = ('username', 'email', 'role', 'phone', 'email_verified', 'is_active', 'is_blocked', 'date_joined')
    list_filter = ('role', 'is_active', 'is_blocked', 'email_verified')
    search_fields = ('username', 'email', 'phone')
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Личная информация', {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        ('Права доступа', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Важные даты', {'fields': ('last_login', 'date_joined')}),
        ('Банковская информация', {'fields': ('email_verified', 'is_blocked', 'blocked_by', 'blocked_at')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'phone', 'password1', 'password2', 'role', 'email_verified'),
        }),
    )


class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'total_invested', 'passport_number', 'birth_date', 'created_at')
    search_fields = ('user__username', 'user__email', 'passport_number')
    list_filter = ('created_at',)
    
    fieldsets = (
        ('Пользователь', {'fields': ('user',)}),
        ('Финансы', {'fields': ('balance', 'total_invested', 'total_profit')}),
        ('Документы', {'fields': ('passport_number', 'birth_date')}),
    )


class AssetAdmin(admin.ModelAdmin):
    list_display = ('symbol', 'name', 'current_price', 'last_update', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('symbol', 'name')
    list_editable = ('current_price', 'is_active')


class PortfolioItemAdmin(admin.ModelAdmin):
    list_display = ('client', 'asset', 'quantity', 'average_buy_price', 'current_value_display')
    search_fields = ('client__username', 'asset__symbol')
    
    def current_value_display(self, obj):
        return f"{obj.current_value():,.2f} ₽"
    current_value_display.short_description = 'Текущая стоимость'


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'type', 'asset', 'amount', 'commission', 'status', 'created_at')
    list_filter = ('type', 'status', 'created_at')
    search_fields = ('client__username', 'asset__symbol')
    readonly_fields = ('created_at',)


class WithdrawRequestAdmin(admin.ModelAdmin):
    list_display = ('client', 'amount', 'status', 'created_at', 'processed_by')
    list_filter = ('status', 'created_at')
    search_fields = ('client__username',)


class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'tax_id', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('name', 'tax_id')


class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'company', 'email', 'salary')
    search_fields = ('full_name', 'email', 'company__name')


class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('asset', 'price', 'timestamp')
    list_filter = ('asset', 'timestamp')
    readonly_fields = ('timestamp',)


class SystemLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'action', 'ip_address')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'action')
    readonly_fields = ('created_at',)


class CommissionSettingsAdmin(admin.ModelAdmin):
    list_display = ('commission_percent', 'updated_at', 'updated_by')
    
    def has_add_permission(self, request):
        return not CommissionSettings.objects.exists()


# Регистрация всех моделей
admin.site.register(User, CustomUserAdmin)
admin.site.register(ClientProfile, ClientProfileAdmin)
admin.site.register(Asset, AssetAdmin)
admin.site.register(PortfolioItem, PortfolioItemAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(WithdrawRequest, WithdrawRequestAdmin)
admin.site.register(Company, CompanyAdmin)
admin.site.register(Employee, EmployeeAdmin)
admin.site.register(PriceHistory, PriceHistoryAdmin)
admin.site.register(SystemLog, SystemLogAdmin)
admin.site.register(CommissionSettings, CommissionSettingsAdmin)
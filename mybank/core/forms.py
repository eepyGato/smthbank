# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from .models import (
    Transaction, WithdrawRequest, Company, Employee,
    CommissionSettings, Asset, EmailVerificationToken
)
import re
from datetime import date
from .models import User, ClientProfile

User = get_user_model()


class PhoneNumberMixin:
    """Mixin для валидации телефона"""
    
    def validate_phone(self, phone):
        pattern = r'^\+375\s\(\d{2}\)\s\d{3}-\d{2}-\d{2}$'
        if not re.match(pattern, phone):
            raise ValidationError(
                'Телефон должен быть в формате +375 (29) XXX-XX-XX'
            )
        return phone


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email')
    first_name = forms.CharField(max_length=100, required=True, label='Имя')
    last_name = forms.CharField(max_length=100, required=True, label='Фамилия')
    middle_name = forms.CharField(max_length=100, required=False, label='Отчество')
    phone = forms.CharField(max_length=20, required=True, label='Телефон')
    passport_number = forms.CharField(max_length=20, required=True, label='Номер паспорта')
    birth_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=True,
        label='Дата рождения'
    )
    address = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=True, label='Адрес')
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2')
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError('Пользователь с таким email уже существует')
        return email
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        import re
        if not re.match(r'^\+375\s\(\d{2}\)\s\d{3}-\d{2}-\d{2}$', phone):
            raise ValidationError('Телефон должен быть в формате +375 (29) XXX-XX-XX')
        if User.objects.filter(phone=phone).exists():
            raise ValidationError('Пользователь с таким телефоном уже существует')
        return phone
    
    def clean_passport_number(self):
        passport = self.cleaned_data.get('passport_number')
        if ClientProfile.objects.filter(passport_number=passport).exists():
            raise ValidationError('Клиент с таким номером паспорта уже зарегистрирован')
        return passport
    
    def clean_birth_date(self):
        birth_date = self.cleaned_data.get('birth_date')
        from datetime import date
        today = date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        if age < 18:
            raise ValidationError('Вам должно быть 18 лет или больше')
        return birth_date
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_active = False
        if commit:
            user.save()
            ClientProfile.objects.create(
                user=user,
                passport_number=self.cleaned_data['passport_number'],
                birth_date=self.cleaned_data['birth_date']
            )
        return user


class DepositForm(forms.Form):
    """Форма пополнения счёта"""
    
    amount = forms.DecimalField(
        max_digits=15, decimal_places=2,
        min_value=1, label='Сумма пополнения',
        widget=forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Введите сумму'})
    )
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise ValidationError('Сумма должна быть больше 0')
        return amount


class WithdrawForm(forms.Form):
    """Форма создания заявки на вывод"""
    
    amount = forms.DecimalField(
        max_digits=15, decimal_places=2,
        min_value=1, label='Сумма вывода',
        widget=forms.NumberInput(attrs={'step': '0.01', 'placeholder': 'Введите сумму'})
    )
    
    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        super().__init__(*args, **kwargs)
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise ValidationError('Сумма должна быть больше 0')
        if self.client and amount > self.client.profile.balance:
            raise ValidationError(f'Недостаточно средств. Ваш баланс: {self.client.profile.balance} ₽')
        return amount


class BuyAssetForm(forms.Form):
    """Форма покупки акций"""
    
    quantity = forms.DecimalField(
        max_digits=15, decimal_places=6,
        min_value=0.000001, label='Количество',
        widget=forms.NumberInput(attrs={'step': '0.000001', 'placeholder': 'Введите количество'})
    )
    
    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        self.asset = kwargs.pop('asset', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity')
        
        if not self.asset:
            raise ValidationError('Актив не найден')
        
        if not self.asset.is_active:
            raise ValidationError('Этот актив временно недоступен для торгов')
        
        if quantity:
            total_cost = quantity * self.asset.current_price
            from .models import CommissionSettings
            commission = CommissionSettings.get_current()
            commission_amount = total_cost * commission.commission_percent / 100
            total_with_commission = total_cost + commission_amount
            
            if self.client and total_with_commission > self.client.profile.balance:
                raise ValidationError(
                    f'Недостаточно средств. Требуется: {total_with_commission:.2f} ₽ '
                    f'(включая комиссию {commission.commission_percent}%). '
                    f'Ваш баланс: {self.client.profile.balance} ₽'
                )
        
        return cleaned_data


class SellAssetForm(forms.Form):
    """Форма продажи акций"""
    
    quantity = forms.DecimalField(
        max_digits=15, decimal_places=6,
        min_value=0.000001, label='Количество',
        widget=forms.NumberInput(attrs={'step': '0.000001', 'placeholder': 'Введите количество'})
    )
    
    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop('client', None)
        self.portfolio_item = kwargs.pop('portfolio_item', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get('quantity')
        
        if not self.portfolio_item:
            raise ValidationError('Позиция не найдена')
        
        if quantity and quantity > self.portfolio_item.quantity:
            raise ValidationError(
                f'У вас только {self.portfolio_item.quantity} акций. '
                f'Вы пытаетесь продать {quantity}'
            )
        
        return cleaned_data


class WithdrawRequestForm(forms.ModelForm):
    """Форма заявки на вывод (для менеджера)"""
    
    class Meta:
        model = WithdrawRequest
        fields = ('status', 'comment')
        widgets = {
            'status': forms.Select(choices=[('completed', 'Подтвердить'), ('cancelled', 'Отклонить')]),
            'comment': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Комментарий (причина отказа)'}),
        }


class CompanyRequestForm(forms.ModelForm):
    """Форма заявки на зарплатный проект"""
    
    class Meta:
        model = Company
        fields = ('name', 'tax_id', 'address')
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }


class CompanyApproveForm(forms.Form):
    """Форма одобрения заявки предприятия (для менеджера)"""
    
    approve = forms.BooleanField(required=True, initial=True, widget=forms.HiddenInput)
    comment = forms.CharField(max_length=500, required=False, label='Комментарий',
                              widget=forms.Textarea(attrs={'rows': 2}))


class EmployeeForm(forms.ModelForm):
    """Форма добавления сотрудника"""
    
    class Meta:
        model = Employee
        fields = ('full_name', 'phone', 'email', 'salary')
        widgets = {
            'salary': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        pattern = r'^\+375\s\(\d{2}\)\s\d{3}-\d{2}-\d{2}$'
        if not re.match(pattern, phone):
            raise ValidationError('Телефон должен быть в формате +375 (29) XXX-XX-XX')
        return phone


class CommissionSettingsForm(forms.ModelForm):
    """Форма настройки комиссии"""
    
    class Meta:
        model = CommissionSettings
        fields = ('commission_percent',)
        widgets = {
            'commission_percent': forms.NumberInput(attrs={'step': '0.01', 'min': 0, 'max': 100}),
        }


class AssetForm(forms.ModelForm):
    """Форма добавления/редактирования актива"""
    
    class Meta:
        model = Asset
        fields = ('symbol', 'name', 'current_price', 'is_active', 'icon')
        widgets = {
            'current_price': forms.NumberInput(attrs={'step': '0.01'}),
        }
    
    def clean_symbol(self):
        symbol = self.cleaned_data.get('symbol')
        symbol = symbol.upper().strip()
        return symbol
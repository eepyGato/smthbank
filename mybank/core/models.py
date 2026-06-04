# core/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
#from django_cryptography.fields import encrypt
from datetime import date
import logging

logger = logging.getLogger(__name__)


class User(AbstractUser):
    """Расширенная модель пользователя"""
    ROLE_CHOICES = (
        ('client', 'Клиент'),
        ('manager', 'Менеджер'),
        ('admin', 'Администратор'),
    )
    role = models.CharField("Роль", max_length=20, choices=ROLE_CHOICES, default='client')
    phone = models.CharField("Телефон", max_length=20, blank=True)
    email_verified = models.BooleanField("Email подтверждён", default=False)
    is_blocked = models.BooleanField("Заблокирован", default=False)
    blocked_at = models.DateTimeField("Дата блокировки", null=True, blank=True)
    blocked_by = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Кем заблокирован"
    )
    created_at = models.DateTimeField("Дата регистрации", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ['-date_joined']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def activate(self):
        """Активация аккаунта"""
        self.is_active = True
        self.save()
        logger.info(f"Пользователь {self.username} активирован")

    def block(self, admin_user, reason=''):
        """Блокировка пользователя"""
        self.is_active = False
        self.is_blocked = True
        self.blocked_at = timezone.now()
        self.blocked_by = admin_user
        self.save()
        logger.info(f"Пользователь {self.username} заблокирован администратором {admin_user.username}")


class ClientProfile(models.Model):
    """Профиль клиента (финансовая информация)"""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile',
        verbose_name="Пользователь"
    )
    balance = models.DecimalField(
        "Баланс", max_digits=15, decimal_places=2, default=0.00,
        validators=[MinValueValidator(0)]
    )
    total_invested = models.DecimalField(
        "Всего инвестировано", max_digits=15, decimal_places=2, default=0.00
    )
    total_profit = models.DecimalField(
        "Общая прибыль", max_digits=15, decimal_places=2, default=0.00
    )
    # ДОБАВЬТЕ ЭТИ ПОЛЯ
    passport_number = models.CharField(
        "Номер паспорта", max_length=20, unique=True, blank=True, null=True
    )
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Профиль клиента"
        verbose_name_plural = "Профили клиентов"

    def __str__(self):
        return f"Профиль {self.user.username}: {self.balance} ₽"
    
    def age(self):
        """Возвращает возраст клиента"""
        from datetime import date
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None


class Asset(models.Model):
    """Биржевой актив (акция, индекс, криптовалюта)"""
    symbol = models.CharField("Тикер", max_length=20, unique=True)
    name = models.CharField("Название", max_length=100)
    current_price = models.DecimalField(
        "Текущая цена", max_digits=12, decimal_places=2, default=0.00
    )
    last_update = models.DateTimeField("Последнее обновление", auto_now=True)
    is_active = models.BooleanField("Доступен для торгов", default=True)
    icon = models.ImageField("Иконка", upload_to='assets/', blank=True, null=True)

    class Meta:
        verbose_name = "Актив"
        verbose_name_plural = "Активы"
        ordering = ['symbol']

    def __str__(self):
        return f"{self.symbol} - {self.name} ({self.current_price} ₽)"


class PortfolioItem(models.Model):
    """Позиция в портфеле клиента"""
    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='portfolio',
        verbose_name="Клиент"
    )
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, verbose_name="Актив"
    )
    quantity = models.DecimalField(
        "Количество", max_digits=15, decimal_places=6, default=0
    )
    average_buy_price = models.DecimalField(
        "Средняя цена покупки", max_digits=12, decimal_places=2, default=0.00
    )
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Позиция портфеля"
        verbose_name_plural = "Позиции портфеля"
        unique_together = ('client', 'asset')

    def current_value(self):
        """Текущая стоимость позиции"""
        return self.quantity * self.asset.current_price

    def profit_loss(self):
        """Прибыль/убыток в деньгах"""
        return self.current_value() - (self.quantity * self.average_buy_price)

    def profit_loss_percent(self):
        """Прибыль/убыток в процентах"""
        cost = self.quantity * self.average_buy_price
        if cost == 0:
            return 0
        return (self.profit_loss() / cost) * 100

    def __str__(self):
        return f"{self.client.username} - {self.asset.symbol}: {self.quantity}"


class Transaction(models.Model):
    """Транзакция (история операций)"""
    TYPE_CHOICES = (
        ('deposit', 'Пополнение'),
        ('withdraw', 'Вывод'),
        ('buy', 'Покупка'),
        ('sell', 'Продажа'),
        ('commission', 'Комиссия'),
    )
    STATUS_CHOICES = (
        ('pending', 'Ожидает'),
        ('completed', 'Выполнено'),
        ('cancelled', 'Отменено'),
    )

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='transactions',
        verbose_name="Клиент"
    )
    type = models.CharField("Тип", max_length=20, choices=TYPE_CHOICES)
    asset = models.ForeignKey(
        Asset, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Актив"
    )
    quantity = models.DecimalField(
        "Количество", max_digits=15, decimal_places=6, null=True, blank=True
    )
    price = models.DecimalField(
        "Цена", max_digits=12, decimal_places=2, null=True, blank=True
    )
    amount = models.DecimalField("Сумма", max_digits=15, decimal_places=2)
    commission = models.DecimalField("Комиссия", max_digits=10, decimal_places=2, default=0)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    processed_at = models.DateTimeField("Дата обработки", null=True, blank=True)
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='processed_transactions', verbose_name="Обработал"
    )
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Транзакция"
        verbose_name_plural = "Транзакции"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['client', 'created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['type']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} - {self.client.username} - {self.amount} ₽"


class WithdrawRequest(models.Model):
    """Заявка на вывод средств"""
    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='withdraw_requests',
        verbose_name="Клиент"
    )
    amount = models.DecimalField("Сумма", max_digits=15, decimal_places=2)
    status = models.CharField(
        "Статус", max_length=20,
        choices=Transaction.STATUS_CHOICES, default='pending'
    )
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    processed_at = models.DateTimeField("Дата обработки", null=True, blank=True)
    processed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Обработал"
    )
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "Заявка на вывод"
        verbose_name_plural = "Заявки на вывод"
        ordering = ['-created_at']

    def __str__(self):
        return f"Заявка {self.client.username} на {self.amount} ₽ - {self.get_status_display()}"


class Company(models.Model):
    """Предприятие (для зарплатного проекта)"""
    STATUS_CHOICES = (
        ('pending', 'Ожидает'),
        ('active', 'Активен'),
        ('rejected', 'Отклонён'),
    )

    name = models.CharField("Название", max_length=200)
    tax_id = models.CharField("ИНН", max_length=20, unique=True)
    address = models.TextField("Адрес")
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Одобрил"
    )
    approved_at = models.DateTimeField("Дата одобрения", null=True, blank=True)

    class Meta:
        verbose_name = "Предприятие"
        verbose_name_plural = "Предприятия"
        ordering = ['name']

    def __str__(self):
        return self.name


class Employee(models.Model):
    """Сотрудник предприятия"""
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name='employees',
        verbose_name="Предприятие"
    )
    full_name = models.CharField("ФИО", max_length=200)
    phone = models.CharField("Телефон", max_length=20)
    email = models.EmailField("Email")
    salary = models.DecimalField("Зарплата", max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField("Дата добавления", auto_now_add=True)

    class Meta:
        verbose_name = "Сотрудник"
        verbose_name_plural = "Сотрудники"
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} - {self.company.name}"


class PriceHistory(models.Model):
    """История цен активов (для графиков)"""
    asset = models.ForeignKey(
        Asset, on_delete=models.CASCADE, related_name='price_history',
        verbose_name="Актив"
    )
    price = models.DecimalField("Цена", max_digits=12, decimal_places=2)
    timestamp = models.DateTimeField("Время", auto_now_add=True)

    class Meta:
        verbose_name = "История цены"
        verbose_name_plural = "История цен"
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['asset', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.asset.symbol} - {self.price} ₽ ({self.timestamp})"


class SystemLog(models.Model):
    """Системный лог действий пользователей"""
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Пользователь"
    )
    action = models.CharField("Действие", max_length=255)
    details = models.TextField("Детали", blank=True)
    ip_address = models.GenericIPAddressField("IP-адрес", null=True, blank=True)
    created_at = models.DateTimeField("Время", auto_now_add=True)

    class Meta:
        verbose_name = "Системный лог"
        verbose_name_plural = "Системные логи"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.created_at} - {self.user} - {self.action[:50]}"


class EmailVerificationToken(models.Model):
    """Токен для подтверждения email"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return (timezone.now() - self.created_at).days > 7

    def __str__(self):
        return f"Токен для {self.user.email} ({'использован' if self.is_used else 'активен'})"


class CommissionSettings(models.Model):
    """Глобальные настройки комиссии"""
    commission_percent = models.DecimalField(
        "Комиссия (%)", max_digits=5, decimal_places=2, default=0.5
    )
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name="Обновил"
    )

    class Meta:
        verbose_name = "Настройка комиссии"
        verbose_name_plural = "Настройки комиссии"

    @classmethod
    def get_current(cls):
        obj, created = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self):
        return f"Комиссия: {self.commission_percent}%"
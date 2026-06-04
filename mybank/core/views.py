# core/views.py (часть 1 - публичные страницы и аутентификация)
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from decimal import Decimal
import logging

from .models import (
    User, ClientProfile, Asset, PortfolioItem, Transaction,
    WithdrawRequest, Company, Employee, PriceHistory, SystemLog,
    CommissionSettings, EmailVerificationToken
)
from .forms import (
    UserRegistrationForm, DepositForm, WithdrawForm,
    BuyAssetForm, SellAssetForm, WithdrawRequestForm,
    CompanyRequestForm, CompanyApproveForm, EmployeeForm,
    CommissionSettingsForm, AssetForm
)
from .decorators import client_required, manager_required, admin_required

logger = logging.getLogger(__name__)


# ==================== ПУБЛИЧНЫЕ СТРАНИЦЫ ====================

from .models import Asset

from .models import Asset, PriceHistory, CommissionSettings
from django.utils import timezone
from datetime import timedelta

def home(request):
    """Главная страница с биржевыми индексами"""
    indices = Asset.objects.filter(
        is_active=True, 
        symbol__in=['^GSPC', '^IXIC', '^DJI', 'GC=F', 'BTC-USD']
    )
    
    for index in indices:
        # Получаем текущую и предыдущую цену
        current_price = float(index.current_price)
        
        # Ищем предыдущую цену из истории
        prev_history = PriceHistory.objects.filter(
            asset=index
        ).exclude(price=current_price).order_by('-timestamp').first()
        
        if prev_history:
            old_price = float(prev_history.price)
            change_percent = ((current_price - old_price) / old_price) * 100
            index.change_percent = round(change_percent, 2)
        else:
            # Если нет истории, генерируем случайное изменение
            import random
            change_percent = random.uniform(-3, 3)
            index.change_percent = round(change_percent, 2)
        
        index.change_symbol = '▲' if index.change_percent >= 0 else '▼'
        index.change_class = 'text-success' if index.change_percent >= 0 else 'text-danger'
    
    commission = CommissionSettings.get_current()
    
    context = {
        'indices': indices,
        'commission': commission,
    }
    return render(request, 'home.html', context)

def about(request):
    """Страница о компании"""
    return render(request, 'about.html')


def faq(request):
    """Страница FAQ"""
    faqs = [
        {'question': 'Как пополнить счёт?', 'answer': 'Перейдите в раздел "Счёт" и нажмите "Пополнить".'},
        {'question': 'Как вывести деньги?', 'answer': 'Создайте заявку на вывод в разделе "Счёт". Менеджер рассмотрит её.'},
        {'question': 'Какая комиссия за сделки?', 'answer': f'Комиссия составляет {CommissionSettings.get_current().commission_percent}% от суммы сделки.'},
        {'question': 'Как купить акции?', 'answer': 'Перейдите в раздел "Рынок", выберите актив и нажмите "Купить".'},
        {'question': 'Как долго обрабатывается заявка на вывод?', 'answer': 'Обычно в течение 1-2 рабочих дней.'},
    ]
    return render(request, 'faq.html', {'faqs': faqs})


def contacts(request):
    """Страница контактов"""
    return render(request, 'contacts.html')


def privacy_policy(request):
    """Страница политики конфиденциальности"""
    return render(request, 'privacy_policy.html')


# ==================== АУТЕНТИФИКАЦИЯ ====================

def register(request):
    """Регистрация нового пользователя"""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Создаём токен для подтверждения email
            token = get_random_string(64)
            EmailVerificationToken.objects.create(user=user, token=token)
            
            # Отправляем письмо
            verify_url = request.build_absolute_uri(f'/verify/{token}/')
            try:
                send_mail(
                    subject='Подтверждение регистрации в MyBank',
                    message=f'Здравствуйте, {user.username}!\n\nДля активации аккаунта перейдите по ссылке:\n{verify_url}\n\nСсылка действительна 7 дней.',
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Ошибка отправки письма: {e}")
            
            messages.success(request, 'Регистрация успешна! Подтвердите email по ссылке в письме.')
            return redirect('login')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'register.html', {'form': form})


def verify_email(request, token):
    """Подтверждение email"""
    try:
        verification = EmailVerificationToken.objects.get(token=token, is_used=False)
        if verification.is_expired():
            messages.error(request, 'Ссылка истекла. Запросите новую.')
            return redirect('register')
        
        user = verification.user
        user.email_verified = True
        user.is_active = True  # Автоматическая активация
        user.save()
        verification.is_used = True
        verification.save()
        
        # Создаём профиль клиента, если его нет
        ClientProfile.objects.get_or_create(user=user)
        
        # Логируем
        SystemLog.objects.create(user=user, action='Подтверждение email', ip_address=request.META.get('REMOTE_ADDR'))
        
        messages.success(request, 'Email подтверждён! Теперь вы можете войти.')
        return redirect('login')
    except EmailVerificationToken.DoesNotExist:
        messages.error(request, 'Неверная ссылка подтверждения.')
        return redirect('register')


# ==================== КЛИЕНТСКАЯ ЧАСТЬ ====================

@login_required
@client_required
def dashboard(request):
    """Личный кабинет клиента"""

    if request.user.role == 'admin':
        return redirect('core:admin_clients')
    if request.user.role == 'manager':
        return redirect('core:manager_clients')
    
    profile = request.user.profile
    
    # Получаем портфель клиента
    portfolio = PortfolioItem.objects.filter(client=request.user).select_related('asset')
    
    # Общая стоимость портфеля
    portfolio_value = sum(item.current_value() for item in portfolio)
    
    # Прибыль/убыток портфеля
    total_cost = sum(item.quantity * item.average_buy_price for item in portfolio)
    total_profit = portfolio_value - total_cost
    profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    # Последние транзакции
    recent_transactions = Transaction.objects.filter(client=request.user).order_by('-created_at')[:10]
    
    # Данные для графика (последние 30 дней)
    chart_data = []
    for i in range(30, 0, -1):
        date = timezone.now() - timezone.timedelta(days=i)
        daily_transactions = Transaction.objects.filter(
            client=request.user,
            created_at__date=date.date()
        ).aggregate(total=Sum('amount'))['total'] or 0
        chart_data.append(float(daily_transactions))
    
    context = {
        'profile': profile,
        'portfolio_value': portfolio_value,
        'total_profit': total_profit,
        'profit_percent': profit_percent,
        'recent_transactions': recent_transactions,
        'chart_data': chart_data,
        'portfolio_items': portfolio,
    }
    return render(request, 'dashboard.html', context)


@login_required
@client_required
def account(request):
    """Управление счётом (пополнение, вывод)"""

    if request.user.role == 'admin':
        return redirect('core:admin_clients')
    if request.user.role == 'manager':
        return redirect('core:manager_clients')
    
    profile = request.user.profile
    
    deposit_form = DepositForm()
    withdraw_form = WithdrawForm(client=request.user)
    
    # Заявки на вывод
    withdraw_requests = WithdrawRequest.objects.filter(client=request.user).order_by('-created_at')
    
    context = {
        'profile': profile,
        'deposit_form': deposit_form,
        'withdraw_form': withdraw_form,
        'withdraw_requests': withdraw_requests,
    }
    return render(request, 'account.html', context)


@login_required
@client_required
def deposit(request):
    """Пополнение счёта (API)"""
    if request.method == 'POST':
        form = DepositForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            # Создаём транзакцию
            transaction = Transaction.objects.create(
                client=request.user,
                type='deposit',
                amount=amount,
                status='completed',
                processed_at=timezone.now()
            )
            
            # Обновляем баланс
            request.user.profile.balance += amount
            request.user.profile.save()
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Пополнение счёта на {amount} ₽',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Счёт пополнен на {amount} ₽')
            return redirect('core:account')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    
    return redirect('core:account')


@login_required
@client_required
def withdraw(request):
    """Создание заявки на вывод"""
    if request.method == 'POST':
        form = WithdrawForm(request.POST, client=request.user)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            # Создаём заявку
            withdraw_request = WithdrawRequest.objects.create(
                client=request.user,
                amount=amount,
                status='pending'
            )
            
            # Создаём транзакцию
            Transaction.objects.create(
                client=request.user,
                type='withdraw',
                amount=amount,
                status='pending',
                comment=f'Заявка #{withdraw_request.id}'
            )
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Создана заявка на вывод {amount} ₽',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Заявка на вывод {amount} ₽ создана. Ожидайте подтверждения менеджера.')
            return redirect('core:account')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    
    return redirect('core:account')


@login_required
@client_required
def market(request):
    """Рынок акций"""

    if request.user.role == 'admin':
        return redirect('core:admin_clients')
    if request.user.role == 'manager':
        return redirect('core:manager_clients')
    
    assets = Asset.objects.filter(is_active=True)
    
    # Обновляем цены (если не обновлялись более 5 минут)
    for asset in assets:
        if not asset.last_update or (timezone.now() - asset.last_update).seconds > 300:
            # TODO: Обновление через Twelve Data API
            pass
    
    context = {
        'assets': assets,
        'commission': CommissionSettings.get_current(),
    }
    return render(request, 'market.html', context)


@login_required
@client_required
def buy_asset(request, asset_id):
    """Покупка акций (API)"""
    asset = get_object_or_404(Asset, id=asset_id, is_active=True)
    
    if request.method == 'POST':
        form = BuyAssetForm(request.POST, client=request.user, asset=asset)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            total_cost = quantity * asset.current_price
            commission = CommissionSettings.get_current()
            commission_amount = total_cost * commission.commission_percent / 100
            total_with_commission = total_cost + commission_amount
            
            # Проверяем баланс
            if total_with_commission > request.user.profile.balance:
                messages.error(request, 'Недостаточно средств')
                return redirect('core:market')
            
            # Создаём транзакцию
            transaction = Transaction.objects.create(
                client=request.user,
                type='buy',
                asset=asset,
                quantity=quantity,
                price=asset.current_price,
                amount=total_cost,
                commission=commission_amount,
                status='completed',
                processed_at=timezone.now()
            )
            
            # Обновляем портфель
            portfolio_item, created = PortfolioItem.objects.get_or_create(
                client=request.user,
                asset=asset,
                defaults={'quantity': 0, 'average_buy_price': 0}
            )
            
            # Пересчитываем среднюю цену
            old_cost = portfolio_item.quantity * portfolio_item.average_buy_price
            new_cost = old_cost + total_cost
            new_quantity = portfolio_item.quantity + quantity
            portfolio_item.average_buy_price = new_cost / new_quantity if new_quantity > 0 else 0
            portfolio_item.quantity = new_quantity
            portfolio_item.save()
            
            # Обновляем баланс
            request.user.profile.balance -= total_with_commission
            request.user.profile.total_invested += total_cost
            request.user.profile.save()
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Покупка {quantity} {asset.symbol} на {total_cost} ₽',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Куплено {quantity} {asset.symbol} на {total_cost} ₽')
            return redirect('core:portfolio')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    
    return redirect('core:market')


@login_required
@client_required
def portfolio(request):
    """Портфель клиента"""

    if request.user.role == 'admin':
        return redirect('core:admin_clients')
    if request.user.role == 'manager':
        return redirect('core:manager_clients')

    portfolio_items = PortfolioItem.objects.filter(client=request.user).select_related('asset')
    
    portfolio_value = sum(item.current_value() for item in portfolio_items)
    total_cost = sum(item.quantity * item.average_buy_price for item in portfolio_items)
    total_profit = portfolio_value - total_cost
    profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
    
    context = {
        'portfolio_items': portfolio_items,
        'portfolio_value': portfolio_value,
        'total_profit': total_profit,
        'profit_percent': profit_percent,
        'commission': CommissionSettings.get_current(),
    }
    return render(request, 'portfolio.html', context)


@login_required
@client_required
def sell_asset(request, item_id):
    """Продажа акций (API)"""
    portfolio_item = get_object_or_404(PortfolioItem, id=item_id, client=request.user)
    
    if request.method == 'POST':
        form = SellAssetForm(request.POST, client=request.user, portfolio_item=portfolio_item)
        if form.is_valid():
            quantity = form.cleaned_data['quantity']
            asset = portfolio_item.asset
            total_revenue = quantity * asset.current_price
            commission = CommissionSettings.get_current()
            commission_amount = total_revenue * commission.commission_percent / 100
            net_revenue = total_revenue - commission_amount
            
            # Создаём транзакцию
            Transaction.objects.create(
                client=request.user,
                type='sell',
                asset=asset,
                quantity=quantity,
                price=asset.current_price,
                amount=total_revenue,
                commission=commission_amount,
                status='completed',
                processed_at=timezone.now()
            )
            
            # Обновляем портфель
            portfolio_item.quantity -= quantity
            
            if portfolio_item.quantity <= 0:
                portfolio_item.delete()
            else:
                portfolio_item.save()
            
            # Обновляем баланс
            request.user.profile.balance += net_revenue
            request.user.profile.total_invested -= total_revenue
            request.user.profile.save()
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Продажа {quantity} {asset.symbol} на {total_revenue} ₽',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Продано {quantity} {asset.symbol} на {total_revenue} ₽ (комиссия {commission_amount} ₽)')
            return redirect('core:portfolio')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    
    return redirect('core:portfolio')


@login_required
@client_required
def transactions(request):
    """История операций"""

    if request.user.role == 'admin':
        return redirect('core:admin_clients')
    if request.user.role == 'manager':
        return redirect('core:manager_clients')
    
    transactions_list = Transaction.objects.filter(client=request.user).order_by('-created_at')
    
    # Фильтрация
    trans_type = request.GET.get('type')
    if trans_type:
        transactions_list = transactions_list.filter(type=trans_type)
    
    date_from = request.GET.get('date_from')
    if date_from:
        transactions_list = transactions_list.filter(created_at__date__gte=date_from)
    
    date_to = request.GET.get('date_to')
    if date_to:
        transactions_list = transactions_list.filter(created_at__date__lte=date_to)
    
    # Пагинация
    paginator = Paginator(transactions_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'transactions': page_obj,
        'filter_type': trans_type,
    }
    return render(request, 'transactions.html', context)

# core/views.py (часть 2 - менеджер и администратор)

# ==================== МЕНЕДЖЕР ====================

@login_required
@manager_required
def manager_clients(request):
    """Список клиентов (менеджер)"""
    clients = User.objects.filter(role='client').order_by('-date_joined')
    
    # Фильтр по статусу
    status = request.GET.get('status')
    if status == 'pending':
        clients = clients.filter(is_active=False, email_verified=False)
    elif status == 'active':
        clients = clients.filter(is_active=True)
    elif status == 'blocked':
        clients = clients.filter(is_blocked=True)
    
    context = {
        'clients': clients,
        'status_filter': status,
    }
    return render(request, 'manager/clients.html', context)


@login_required
@manager_required
def manager_activate_client(request, user_id):
    """Активация клиента менеджером"""
    client = get_object_or_404(User, id=user_id, role='client')
    
    if not client.is_active and client.email_verified:
        client.is_active = True
        client.save()
        
        # Отправляем уведомление
        try:
            send_mail(
                subject='Ваш аккаунт в MyBank активирован!',
                message=f'Здравствуйте, {client.username}!\n\nВаш аккаунт активирован менеджером. Теперь вы можете войти и пользоваться услугами банка.',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[client.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки письма: {e}")
        
        messages.success(request, f'Клиент {client.username} активирован')
        
        # Логируем
        SystemLog.objects.create(
            user=request.user,
            action=f'Активация клиента {client.username}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
    else:
        messages.warning(request, f'Клиент {client.username} не может быть активирован')
    
    return redirect('core:manager_clients')


@login_required
@manager_required
def manager_withdrawals(request):
    """Заявки на вывод (менеджер)"""
    withdraw_requests = WithdrawRequest.objects.filter(status='pending').order_by('-created_at')
    
    if request.method == 'POST':
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        
        withdraw_request = get_object_or_404(WithdrawRequest, id=request_id)
        
        if action == 'approve':
            # Подтверждение заявки
            if withdraw_request.amount <= withdraw_request.client.profile.balance:
                withdraw_request.status = 'completed'
                withdraw_request.processed_at = timezone.now()
                withdraw_request.processed_by = request.user
                withdraw_request.save()
                
                # Списываем деньги
                withdraw_request.client.profile.balance -= withdraw_request.amount
                withdraw_request.client.profile.save()
                
                # Обновляем транзакцию
                transaction = Transaction.objects.filter(
                    client=withdraw_request.client,
                    type='withdraw',
                    status='pending',
                    comment__icontains=f'Заявка #{withdraw_request.id}'
                ).first()
                if transaction:
                    transaction.status = 'completed'
                    transaction.processed_at = timezone.now()
                    transaction.processed_by = request.user
                    transaction.save()
                
                # Отправляем уведомление
                try:
                    send_mail(
                        subject=f'Заявка на вывод {withdraw_request.amount} ₽ подтверждена',
                        message=f'Здравствуйте, {withdraw_request.client.username}!\n\nВаша заявка на вывод {withdraw_request.amount} ₽ подтверждена. Деньги списаны со счёта.',
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[withdraw_request.client.email],
                        fail_silently=False,
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки письма: {e}")
                
                messages.success(request, f'Заявка на вывод {withdraw_request.amount} ₽ подтверждена')
                
                # Логируем
                SystemLog.objects.create(
                    user=request.user,
                    action=f'Подтверждение заявки на вывод {withdraw_request.amount} ₽ от {withdraw_request.client.username}',
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            else:
                messages.error(request, f'Недостаточно средств на счету клиента')
                
        elif action == 'reject':
            # Отклонение заявки
            withdraw_request.status = 'cancelled'
            withdraw_request.processed_at = timezone.now()
            withdraw_request.processed_by = request.user
            withdraw_request.save()
            
            # Обновляем транзакцию
            transaction = Transaction.objects.filter(
                client=withdraw_request.client,
                type='withdraw',
                status='pending',
                comment__icontains=f'Заявка #{withdraw_request.id}'
            ).first()
            if transaction:
                transaction.status = 'cancelled'
                transaction.processed_at = timezone.now()
                transaction.processed_by = request.user
                transaction.save()
            
            # Отправляем уведомление
            try:
                send_mail(
                    subject=f'Заявка на вывод {withdraw_request.amount} ₽ отклонена',
                    message=f'Здравствуйте, {withdraw_request.client.username}!\n\nВаша заявка на вывод {withdraw_request.amount} ₽ отклонена. Деньги остались на счету.',
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[withdraw_request.client.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Ошибка отправки письма: {e}")
            
            messages.info(request, f'Заявка на вывод {withdraw_request.amount} ₽ отклонена')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Отклонение заявки на вывод {withdraw_request.amount} ₽ от {withdraw_request.client.username}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return redirect('core:manager_withdrawals')
    
    context = {
        'withdraw_requests': withdraw_requests,
    }
    return render(request, 'manager/withdrawals.html', context)


@login_required
@manager_required
def manager_company_requests(request):
    """Заявки на зарплатный проект"""
    companies = Company.objects.filter(status='pending').order_by('-created_at')
    
    if request.method == 'POST':
        company_id = request.POST.get('company_id')
        action = request.POST.get('action')
        
        company = get_object_or_404(Company, id=company_id)
        
        if action == 'approve':
            company.status = 'active'
            company.approved_by = request.user
            company.approved_at = timezone.now()
            company.save()
            
            messages.success(request, f'Предприятие {company.name} одобрено')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Одобрение заявки предприятия {company.name}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        elif action == 'reject':
            company.status = 'rejected'
            company.save()
            messages.info(request, f'Предприятие {company.name} отклонено')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Отклонение заявки предприятия {company.name}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return redirect('core:manager_company_requests')
    
    context = {
        'companies': companies,
    }
    return render(request, 'manager/company_requests.html', context)


@login_required
@manager_required
def manager_companies(request):
    """Список активных предприятий"""
    companies = Company.objects.filter(status='active').order_by('name')
    
    context = {
        'companies': companies,
    }
    return render(request, 'manager/companies.html', context)


@login_required
@manager_required
def manager_add_employee(request, company_id):
    """Добавление сотрудника в предприятие"""
    company = get_object_or_404(Company, id=company_id, status='active')
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.company = company
            employee.save()
            
            messages.success(request, f'Сотрудник {employee.full_name} добавлен')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Добавление сотрудника {employee.full_name} в {company.name}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('core:manager_companies')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = EmployeeForm()
    
    context = {
        'form': form,
        'company': company,
    }
    return render(request, 'manager/add_employee.html', context)


@login_required
@manager_required
def manager_transactions(request):
    """История операций всех клиентов (менеджер)"""
    transactions_list = Transaction.objects.select_related('client').order_by('-created_at')
    
    # Фильтр по клиенту
    client_id = request.GET.get('client')
    if client_id:
        transactions_list = transactions_list.filter(client_id=client_id)
    
    # Фильтр по типу
    trans_type = request.GET.get('type')
    if trans_type:
        transactions_list = transactions_list.filter(type=trans_type)
    
    # Пагинация
    paginator = Paginator(transactions_list, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    clients = User.objects.filter(role='client').order_by('username')
    
    context = {
        'transactions': page_obj,
        'clients': clients,
        'selected_client': client_id,
        'filter_type': trans_type,
    }
    return render(request, 'manager/transactions.html', context)


# ==================== АДМИНИСТРАТОР ====================

@login_required
@admin_required
def admin_clients(request):
    """Список клиентов (админ)"""
    clients = User.objects.filter(role='client').order_by('-date_joined')
    
    context = {
        'clients': clients,
    }
    return render(request, 'admin/clients.html', context)


@login_required
@admin_required
def admin_change_balance(request, user_id):
    """Изменение баланса клиента (админ)"""
    client = get_object_or_404(User, id=user_id, role='client')
    
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        operation = request.POST.get('operation')  # add или subtract
        reason = request.POST.get('reason', '')
        
        if operation == 'add':
            client.profile.balance += amount
            Transaction.objects.create(
                client=client,
                type='deposit',
                amount=amount,
                status='completed',
                processed_at=timezone.now(),
                processed_by=request.user,
                comment=f'Ручное изменение баланса админом. Причина: {reason}'
            )
            messages.success(request, f'Баланс {client.username} увеличен на {amount} ₽')
        elif operation == 'subtract':
            if amount <= client.profile.balance:
                client.profile.balance -= amount
                Transaction.objects.create(
                    client=client,
                    type='withdraw',
                    amount=amount,
                    status='completed',
                    processed_at=timezone.now(),
                    processed_by=request.user,
                    comment=f'Ручное изменение баланса админом. Причина: {reason}'
                )
                messages.success(request, f'Баланс {client.username} уменьшен на {amount} ₽')
            else:
                messages.error(request, 'Недостаточно средств на счету клиента')
        
        client.profile.save()
        
        # Отправляем уведомление
        try:
            send_mail(
                subject='Изменение баланса',
                message=f'Здравствуйте, {client.username}!\n\nВаш баланс был изменён администратором. {reason}\nНовый баланс: {client.profile.balance} ₽',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[client.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки письма: {e}")
        
        # Логируем
        SystemLog.objects.create(
            user=request.user,
            action=f'Изменение баланса {client.username}: {operation} {amount} ₽',
            details=reason,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return redirect('core:admin_clients')
    
    context = {
        'client': client,
    }
    return render(request, 'admin/change_balance.html', context)


@login_required
@admin_required
def admin_block_client(request, user_id):
    """Блокировка/разблокировка клиента"""
    client = get_object_or_404(User, id=user_id, role='client')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')
        
        if action == 'block':
            client.is_active = False
            client.is_blocked = True
            client.blocked_at = timezone.now()
            client.blocked_by = request.user
            client.save()
            
            messages.warning(request, f'Клиент {client.username} заблокирован')
            
            # Отправляем уведомление
            try:
                send_mail(
                    subject='Ваш аккаунт заблокирован',
                    message=f'Здравствуйте, {client.username}!\n\nВаш аккаунт был заблокирован администратором. Причина: {reason}',
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[client.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Ошибка отправки письма: {e}")
                
        elif action == 'unblock':
            client.is_active = True
            client.is_blocked = False
            client.blocked_at = None
            client.blocked_by = None
            client.save()
            
            messages.success(request, f'Клиент {client.username} разблокирован')
            
            # Отправляем уведомление
            try:
                send_mail(
                    subject='Ваш аккаунт разблокирован',
                    message=f'Здравствуйте, {client.username}!\n\nВаш аккаунт был разблокирован администратором.',
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[client.email],
                    fail_silently=False,
                )
            except Exception as e:
                logger.error(f"Ошибка отправки письма: {e}")
        
        # Логируем
        SystemLog.objects.create(
            user=request.user,
            action=f'{action.upper()} клиента {client.username}',
            details=reason,
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return redirect('core:admin_clients')
    
    context = {
        'client': client,
    }
    return render(request, 'admin/block_client.html', context)


from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from .decorators import admin_required

@login_required
@admin_required
def admin_managers(request):
    managers = User.objects.filter(role='manager').order_by('-date_joined')
    return render(request, 'admin/managers.html', {'managers': managers})

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User
from .decorators import admin_required

@login_required
@admin_required
def admin_add_manager(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Пользователь с таким именем уже существует')
            return redirect('core:admin_managers')
        User.objects.create_user(
            username=username,
            email=email,
            password=password,
            role='manager',
            is_active=True,
            email_verified=True
        )
        messages.success(request, f'Менеджер {username} создан')
        return redirect('core:admin_managers')
    # Важно: для GET запроса просто показываем форму
    return render(request, 'admin/add_manager.html')


@login_required
@admin_required
def admin_delete_manager(request, user_id):
    manager = get_object_or_404(User, id=user_id, role='manager')
    username = manager.username
    manager.delete()
    messages.success(request, f'Менеджер {username} удалён')
    return redirect('core:admin_managers')


@login_required
@admin_required
def admin_assets(request):
    """Управление активами"""
    assets = Asset.objects.all().order_by('symbol')
    
    context = {
        'assets': assets,
    }
    return render(request, 'admin/assets.html', context)


@login_required
@admin_required
def admin_add_asset(request):
    """Добавление актива"""
    if request.method == 'POST':
        form = AssetForm(request.POST, request.FILES)
        if form.is_valid():
            asset = form.save()
            messages.success(request, f'Актив {asset.symbol} добавлен')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Добавление актива {asset.symbol}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('core:admin_assets')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = AssetForm()
    
    context = {
        'form': form,
    }
    return render(request, 'admin/asset_form.html', context)


@login_required
@admin_required
def admin_edit_asset(request, asset_id):
    """Редактирование актива"""
    asset = get_object_or_404(Asset, id=asset_id)
    
    if request.method == 'POST':
        form = AssetForm(request.POST, request.FILES, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, f'Актив {asset.symbol} обновлён')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Редактирование актива {asset.symbol}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('core:admin_assets')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = AssetForm(instance=asset)
    
    context = {
        'form': form,
        'asset': asset,
    }
    return render(request, 'admin/asset_form.html', context)


@login_required
@admin_required
def admin_delete_asset(request, asset_id):
    """Удаление актива"""
    asset = get_object_or_404(Asset, id=asset_id)
    
    if request.method == 'POST':
        symbol = asset.symbol
        asset.delete()
        
        messages.success(request, f'Актив {symbol} удалён')
        
        # Логируем
        SystemLog.objects.create(
            user=request.user,
            action=f'Удаление актива {symbol}',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return redirect('core:admin_assets')
    
    context = {
        'asset': asset,
    }
    return render(request, 'admin/asset_confirm_delete.html', context)


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .decorators import admin_required
from .models import User, PortfolioItem

@login_required
@admin_required
def admin_margin_call(request):
    """Маржин-колл - список клиентов с убыточными позициями"""
    clients_with_loss = []
    
    print("=== DEBUG margin_call ===")
    
    # Получаем всех клиентов
    clients = User.objects.filter(role='client', is_active=True)
    print(f"Найдено клиентов: {clients.count()}")
    
    for client in clients:
        print(f"\nПроверяем клиента: {client.username}")
        
        # Получаем позиции клиента
        portfolio_items = PortfolioItem.objects.filter(client=client)
        print(f"  Позиций: {portfolio_items.count()}")
        
        if portfolio_items.exists():
            total_value = 0
            total_cost = 0
            
            for item in portfolio_items:
                item_value = item.quantity * item.asset.current_price
                item_cost = item.quantity * item.average_buy_price
                total_value += item_value
                total_cost += item_cost
                print(f"  {item.asset.symbol}: кол-во={item.quantity}, цена покупки={item.average_buy_price}, текущая цена={item.asset.current_price}")
                print(f"    стоимость={item_value}, затрачено={item_cost}")
            
            print(f"  total_value={total_value}, total_cost={total_cost}")
            
            if total_cost > 0:
                loss_percent = ((total_value - total_cost) / total_cost) * 100
                print(f"  loss_percent={loss_percent}%")
                
                if loss_percent <= -30:
                    print(f"  -> ДОБАВЛЯЕМ В СПИСОК!")
                    clients_with_loss.append({
                        'user': client,
                        'loss_percent': round(abs(loss_percent), 2),
                        'portfolio_value': total_value,
                        'portfolio_cost': total_cost,
                        'loss_amount': total_cost - total_value,
                        'portfolio_items': portfolio_items,
                    })
                else:
                    print(f"  -> убыток {loss_percent}% меньше 30%, не добавляем")
            else:
                print(f"  total_cost=0, пропускаем")
        else:
            print(f"  нет позиций")
    
    print(f"\nИтого в списке: {len(clients_with_loss)} клиентов")
    
    context = {
        'clients': clients_with_loss,
    }
    return render(request, 'admin/margin_call.html', context)


@login_required
@admin_required
def admin_margin_call_close(request, user_id):
    """Принудительное закрытие позиций клиента (маржин-колл)"""
    client = get_object_or_404(User, id=user_id, role='client')
    portfolio_items = PortfolioItem.objects.filter(client=client).select_related('asset')
    
    if request.method == 'POST':
        total_revenue = 0
        closed_positions = []
        
        for item in portfolio_items:
            revenue = item.current_value()
            total_revenue += revenue
            closed_positions.append(f"{item.quantity} {item.asset.symbol} на {revenue} ₽")
            
            # Создаём транзакцию на продажу
            Transaction.objects.create(
                client=client,
                type='sell',
                asset=item.asset,
                quantity=item.quantity,
                price=item.asset.current_price,
                amount=revenue,
                status='completed',
                processed_at=timezone.now(),
                processed_by=request.user,
                comment='Принудительное закрытие позиций (Margin Call)'
            )
            
            # Удаляем позицию
            item.delete()
        
        # Обновляем баланс
        client.profile.balance += total_revenue
        client.profile.save()
        
        # Отправляем уведомление
        try:
            send_mail(
                subject='Margin Call - ваши позиции закрыты',
                message=f'Здравствуйте, {client.username}!\n\nВ связи с превышением допустимого уровня убытка, ваши позиции были принудительно закрыты администратором.\n\nЗакрытые позиции:\n' + '\n'.join(closed_positions) + f'\n\nСредства зачислены на баланс: {total_revenue} ₽',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[client.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Ошибка отправки письма: {e}")
        
        messages.success(request, f'Позиции клиента {client.username} закрыты. Зачислено {total_revenue} ₽')
        
        # Логируем
        SystemLog.objects.create(
            user=request.user,
            action=f'Margin Call - закрытие позиций {client.username}',
            details=f'Зачислено {total_revenue} ₽',
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return redirect('core:admin_margin_call')
    
    context = {
        'client': client,
        'portfolio_items': portfolio_items,
        'total_value': sum(item.current_value() for item in portfolio_items),
    }
    return render(request, 'admin/margin_call_confirm.html', context)


@login_required
@admin_required
def admin_commission(request):
    """Настройка комиссии"""
    commission = CommissionSettings.get_current()
    
    if request.method == 'POST':
        form = CommissionSettingsForm(request.POST, instance=commission)
        if form.is_valid():
            commission = form.save(commit=False)
            commission.updated_by = request.user
            commission.save()
            
            messages.success(request, f'Комиссия установлена на {commission.commission_percent}%')
            
            # Логируем
            SystemLog.objects.create(
                user=request.user,
                action=f'Изменение комиссии на {commission.commission_percent}%',
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return redirect('core:admin_commission')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = CommissionSettingsForm(instance=commission)
    
    context = {
        'form': form,
        'commission': commission,
    }
    return render(request, 'admin/commission.html', context)


@login_required
@admin_required
def admin_logs(request):
    """Системные логи"""
    logs = SystemLog.objects.select_related('user').order_by('-created_at')
    
    # Фильтр по пользователю
    user_id = request.GET.get('user')
    if user_id:
        logs = logs.filter(user_id=user_id)
    
    # Фильтр по действию
    action = request.GET.get('action')
    if action:
        logs = logs.filter(action__icontains=action)
    
    # Пагинация
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    users = User.objects.all().order_by('username')
    
    context = {
        'logs': page_obj,
        'users': users,
        'selected_user': user_id,
        'filter_action': action,
    }
    return render(request, 'admin/logs.html', context)

# core/views.py - добавить в конец файла

def manager_process_withdrawal(request, request_id):
    """Обработка заявки на вывод (менеджер)"""
    from .models import WithdrawRequest
    withdraw_request = get_object_or_404(WithdrawRequest, id=request_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            withdraw_request.status = 'completed'
            withdraw_request.processed_at = timezone.now()
            withdraw_request.processed_by = request.user
            withdraw_request.save()
            messages.success(request, f'Заявка на вывод {withdraw_request.amount} ₽ подтверждена')
        elif action == 'reject':
            withdraw_request.status = 'cancelled'
            withdraw_request.processed_at = timezone.now()
            withdraw_request.processed_by = request.user
            withdraw_request.save()
            messages.info(request, f'Заявка на вывод {withdraw_request.amount} ₽ отклонена')
    
    return redirect('core:manager_withdrawals')


def manager_process_company(request, company_id):
    """Обработка заявки предприятия (менеджер)"""
    from .models import Company
    company = get_object_or_404(Company, id=company_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            company.status = 'active'
            company.approved_by = request.user
            company.approved_at = timezone.now()
            company.save()
            messages.success(request, f'Предприятие {company.name} одобрено')
        elif action == 'reject':
            company.status = 'rejected'
            company.save()
            messages.info(request, f'Предприятие {company.name} отклонено')
    
    return redirect('core:manager_company_requests')


def admin_change_balance(request, user_id):
    """Изменение баланса клиента (админ)"""
    from .models import User
    client = get_object_or_404(User, id=user_id, role='client')
    
    if request.method == 'POST':
        amount = Decimal(request.POST.get('amount', 0))
        operation = request.POST.get('operation')
        reason = request.POST.get('reason', '')
        
        if operation == 'add':
            client.profile.balance += amount
            client.profile.save()
            messages.success(request, f'Баланс увеличен на {amount} ₽')
        elif operation == 'subtract':
            if amount <= client.profile.balance:
                client.profile.balance -= amount
                client.profile.save()
                messages.success(request, f'Баланс уменьшен на {amount} ₽')
            else:
                messages.error(request, 'Недостаточно средств')
    
    return redirect('core:admin_clients')


def admin_block_client(request, user_id):
    """Блокировка/разблокировка клиента (админ)"""
    from .models import User
    client = get_object_or_404(User, id=user_id, role='client')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'block':
            client.is_active = False
            client.is_blocked = True
            client.blocked_at = timezone.now()
            client.blocked_by = request.user
            client.save()
            messages.warning(request, f'Клиент {client.username} заблокирован')
        elif action == 'unblock':
            client.is_active = True
            client.is_blocked = False
            client.blocked_at = None
            client.blocked_by = None
            client.save()
            messages.success(request, f'Клиент {client.username} разблокирован')
    
    return redirect('core:admin_clients')


def admin_add_manager(request):
    """Добавление менеджера (админ)"""
    from .models import User
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        
        if not User.objects.filter(username=username).exists():
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='manager',
                is_active=True,
                email_verified=True
            )
            messages.success(request, f'Менеджер {username} создан')
        else:
            messages.error(request, 'Пользователь с таким именем уже существует')
    
    return redirect('core:admin_managers')


def admin_delete_manager(request, user_id):
    """Удаление менеджера (админ)"""
    from .models import User
    manager = get_object_or_404(User, id=user_id, role='manager')
    username = manager.username
    manager.delete()
    messages.success(request, f'Менеджер {username} удалён')
    return redirect('core:admin_managers')


def admin_edit_asset(request, asset_id):
    """Редактирование актива (админ)"""
    from .models import Asset
    asset = get_object_or_404(Asset, id=asset_id)
    
    if request.method == 'POST':
        form = AssetForm(request.POST, request.FILES, instance=asset)
        if form.is_valid():
            form.save()
            messages.success(request, f'Актив {asset.symbol} обновлён')
        else:
            for error in form.errors.values():
                messages.error(request, error)
        return redirect('core:admin_assets')
    
    form = AssetForm(instance=asset)
    return render(request, 'admin/asset_form.html', {'form': form, 'asset': asset})


def admin_delete_asset(request, asset_id):
    """Удаление актива (админ)"""
    from .models import Asset
    asset = get_object_or_404(Asset, id=asset_id)
    symbol = asset.symbol
    asset.delete()
    messages.success(request, f'Актив {symbol} удалён')
    return redirect('core:admin_assets')


def admin_margin_call_close(request, user_id):
    """Закрытие позиций клиента (маржин-колл)"""
    from .models import User, PortfolioItem, Transaction, CommissionSettings
    client = get_object_or_404(User, id=user_id, role='client')
    portfolio_items = PortfolioItem.objects.filter(client=client)
    
    if request.method == 'POST':
        total_revenue = 0
        for item in portfolio_items:
            revenue = item.current_value()
            total_revenue += revenue
            Transaction.objects.create(
                client=client,
                type='sell',
                asset=item.asset,
                quantity=item.quantity,
                price=item.asset.current_price,
                amount=revenue,
                status='completed',
                processed_at=timezone.now(),
                processed_by=request.user,
                comment='Принудительное закрытие позиций (Margin Call)'
            )
            item.delete()
        
        client.profile.balance += total_revenue
        client.profile.save()
        messages.success(request, f'Позиции клиента {client.username} закрыты. Зачислено {total_revenue} ₽')
    
    return redirect('core:admin_margin_call')
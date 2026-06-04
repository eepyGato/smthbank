# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Публичные страницы
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('faq/', views.faq, name='faq'),
    path('contacts/', views.contacts, name='contacts'),
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    
    # Аутентификация
    path('register/', views.register, name='register'),
    path('verify/<str:token>/', views.verify_email, name='verify_email'),
    
    # Клиентские страницы
    path('dashboard/', views.dashboard, name='dashboard'),
    path('account/', views.account, name='account'),
    path('market/', views.market, name='market'),
    path('portfolio/', views.portfolio, name='portfolio'),
    path('transactions/', views.transactions, name='transactions'),
    
    # API
    path('api/deposit/', views.deposit, name='deposit'),
    path('api/withdraw/', views.withdraw, name='withdraw'),
    path('api/buy/<int:asset_id>/', views.buy_asset, name='buy_asset'),
    path('api/sell/<int:item_id>/', views.sell_asset, name='sell_asset'),
    
    # Менеджер
    path('manager/clients/', views.manager_clients, name='manager_clients'),
    path('manager/clients/activate/<int:user_id>/', views.manager_activate_client, name='manager_activate_client'),
    path('manager/withdrawals/', views.manager_withdrawals, name='manager_withdrawals'),
    path('manager/withdrawals/process/<int:request_id>/', views.manager_process_withdrawal, name='manager_process_withdrawal'),
    path('manager/company-requests/', views.manager_company_requests, name='manager_company_requests'),
    path('manager/company-requests/process/<int:company_id>/', views.manager_process_company, name='manager_process_company'),
    path('manager/companies/', views.manager_companies, name='manager_companies'),
    path('manager/companies/<int:company_id>/add-employee/', views.manager_add_employee, name='manager_add_employee'),
    path('manager/transactions/', views.manager_transactions, name='manager_transactions'),
    
    # Администратор
    path('admin/clients/', views.admin_clients, name='admin_clients'),
    path('admin/clients/<int:user_id>/balance/', views.admin_change_balance, name='admin_change_balance'),
    path('admin/clients/<int:user_id>/block/', views.admin_block_client, name='admin_block_client'),
    path('admin/managers/', views.admin_managers, name='admin_managers'),
    path('admin/managers/add/', views.admin_add_manager, name='admin_add_manager'),
    path('admin/managers/<int:user_id>/delete/', views.admin_delete_manager, name='admin_delete_manager'),
    path('admin/assets/', views.admin_assets, name='admin_assets'),
    path('admin/assets/add/', views.admin_add_asset, name='admin_add_asset'),
    path('admin/assets/<int:asset_id>/edit/', views.admin_edit_asset, name='admin_edit_asset'),
    path('admin/assets/<int:asset_id>/delete/', views.admin_delete_asset, name='admin_delete_asset'),
    path('admin/margin-call/', views.admin_margin_call, name='admin_margin_call'),
    path('admin/margin-call/<int:user_id>/', views.admin_margin_call_close, name='admin_margin_call_close'),
    path('admin/commission/', views.admin_commission, name='admin_commission'),
    path('admin/logs/', views.admin_logs, name='admin_logs'),
]
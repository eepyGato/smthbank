# import logging
# import yfinance as yf
# from celery import shared_task
# from .models import Asset, PriceHistory

# logger = logging.getLogger(__name__)

# @shared_task
# def update_all_stock_prices():
#     """Обновление цен акций через Yahoo Finance"""
    
#     assets = Asset.objects.filter(is_active=True)
#     if not assets:
#         logger.info("No assets to update")
#         return
    
#     for asset in assets:
#         try:
#             ticker = yf.Ticker(asset.symbol)
#             data = ticker.history(period="1d")
            
#             if not data.empty:
#                 new_price = float(data['Close'].iloc[-1])
#                 old_price = float(asset.current_price)
                
#                 # Используем простой текст без стрелок
#                 logger.info(f"{asset.symbol}: {old_price} -> {new_price:.2f}")
                
#                 asset.current_price = new_price
#                 asset.save()
#                 PriceHistory.objects.create(asset=asset, price=new_price)
#             else:
#                 logger.warning(f"No data for {asset.symbol}")
                
#         except Exception as e:
#             logger.error(f"Error {asset.symbol}: {e}")
    
#     logger.info("Price update completed")
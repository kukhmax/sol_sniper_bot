from solders.pubkey import Pubkey
from solana.rpc.api import Client
import requests
import time
from decimal import Decimal
import json
from termcolor import colored, cprint

class RaydiumPnLTracker:
    def __init__(self, rpc_url="https://api.mainnet-beta.solana.com"):
        self.client = Client(rpc_url)
        
    def get_pool_price(self, pool_address: str) -> Decimal:
        """
        Получает текущую цену пула на Raydium
        
        Args:
            pool_address (str): Адрес пула ликвидности
        Returns:
            Decimal: Текущая цена токена
        """
        try:
            # Получаем данные пула через Raydium API
            # true = True
            while True:
                response = requests.get(f"https://api-v3.raydium.io/pools/info/ids?ids={pool_address}")
                pool_data = response.json()
                current_price = 0
                # print(f"Data is {pool_data}")
                if pool_data['data'] != [None]:
                    if pool_data['data'][0]['mintA']['symbol'] == "WSOL":
                        cprint(f"Данные пула: {pool_data['data'][0]['mintB']['name']}", "grey", attrs=["bold"])
                        decimals = int(pool_data['data'][0]['mintA']['decimals'])
                        cur_price = float(Decimal(str(pool_data['data'][0]['price'])))
                        if cur_price > 0:
                            print(type(cur_price))
                            current_price = 1 / cur_price
                            print(f"Current price: {current_price:.9f}")
                            return round(current_price, decimals)
                    else:
                        cprint(f"Данные пула: {pool_data['data'][0]['mintA']['name']}", "grey", attrs=["bold"])
                        decimals = int(pool_data['data'][0]['mintA']['decimals'])
                        current_price = Decimal(str(pool_data['data'][0]['price']))
                        
                    time.sleep(0.5)

                if current_price == 0:
                    continue
                else:             
                    return round(current_price, decimals)
                

            
            # Извлекаем текущую цену
            
            
            
        except Exception as e:
            cprint(f"Ошибка при получении цены: {e}", "red", attrs=["bold", "reverse"])
            return None

    def calculate_pnl(self, purchase_price: Decimal, current_price: Decimal) -> Decimal:
        """
        Рассчитывает PnL в процентах
        
        Args:
            purchase_price (Decimal): Цена покупки
            current_price (Decimal): Текущая цена
        Returns:
            Decimal: PnL в процентах
        """
        return ((current_price - purchase_price) / purchase_price) * 100

    def monitor_pool(self, pool_address: str, purchase_price: Decimal, tokens_amount: Decimal, 
                    check_interval: int = 60):
        """
        Мониторит пул и выводит PnL
        
        Args:
            pool_address (str): Адрес пула
            purchase_price (Decimal): Цена покупки
            tokens_amount (Decimal): Количество купленных токенов
            check_interval (int): Интервал проверки в секундах
        """
        cprint(f"Начинаем мониторинг пула: {pool_address}", "green", attrs=["bold"])
        cprint(f"Цена покупки: {purchase_price:.9f}", "grey", "on_light_magenta")
        cprint(f"Количество токенов: {tokens_amount}", "white", "on_light_blue", attrs=["bold"])
        
        while True:
            try:
                current_price = self.get_pool_price(pool_address)
                if current_price:
                    pnl_percentage = self.calculate_pnl(purchase_price, current_price)
                    initial_value = purchase_price * tokens_amount
                    current_value = current_price * tokens_amount
                    absolute_pnl = current_value - initial_value
                    
                    color_pnl = "green" if pnl_percentage >= 0 else "red"

                    cprint("="*25, "yellow", attrs=["bold"])
                    cprint(f"Текущая цена: {current_price}", "yellow", attrs=["bold"])
                    cprint(f"PnL (%): {pnl_percentage:.2f}%", color_pnl, attrs=["bold"])
                    cprint(f"PnL (SOL): {absolute_pnl:.2f}", "white", attrs=["bold"])
                    cprint(f"Текущая стоимость: {current_value:.2f}", "yellow", attrs=["bold"])
                    cprint("="*25, "yellow", attrs=["bold"])
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                cprint("\nМониторинг остановлен пользователем", "red", attrs=["bold", "reverse"])
                break
            except Exception as e:
                cprint(f"Произошла ошибка: {e}", "red", attrs=["bold", "reverse"])
                time.sleep(check_interval)

def main(pool_id, buy_price, tokens_amount):
    # Пример использования
    tracker = RaydiumPnLTracker()
    
    tracker.monitor_pool(
        pool_address=POOL_ADDRESS,
        purchase_price=PURCHASE_PRICE,
        tokens_amount=TOKENS_AMOUNT,
        check_interval=20  # Проверка каждую минуту
    )

if __name__ == "__main__":
    # Замените эти значения на свои
    POOL_ADDRESS = "F8zGzT9FgeU47oGDdyr42N7Dy47xbC1oyweLg5QsARsR"
    PURCHASE_PRICE = Decimal("0.00000007482")  # Цена покупки
    TOKENS_AMOUNT = Decimal("10000")    # Количество токенов

    main(POOL_ADDRESS, PURCHASE_PRICE, TOKENS_AMOUNT)
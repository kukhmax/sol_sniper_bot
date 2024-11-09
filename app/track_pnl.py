import base58
from solana.rpc.api import Client
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
import pandas as pd

from termcolor import colored, cprint


class RaydiumPnLTracker:
    def __init__(self, pool_id, from_token, to_token, rpc_url="https://api.mainnet-beta.solana.com"):
        self.client = Client(rpc_url)
        self.pool_id = pool_id
        self.from_token = from_token
        self.to_token = to_token

    def get_current_transaction(self):
        # try:
            # Получаем список подписей транзакций для этого пула
            signatures_response = self.client.get_signatures_for_address(self.pool_id)

            # Проверяем, успешен ли запрос
            if signatures_response is not None and signatures_response.value:
                # Получаем подпись последней транзакции
                latest_signature = signatures_response.value[0].signature
            
                price = self.get_current_price(latest_signature)
                return price
            
        # except Exception as e:
        #     cprint(f"Error while getting current transaction: {str(e)}", "red", attrs=["bold", "reverse"])

    def get_current_price(self,signature):
        # try:
            # Устанавливаем параметры напрямую
            encoding = "jsonParsed"
            max_supported_transaction_version = 0

            # Получаем информацию о последней транзакции по подписи
            transaction_response = self.client.get_transaction(
                signature,
                encoding=encoding,
                max_supported_transaction_version=max_supported_transaction_version
            )

            # Проверяем, что данные получены
            if transaction_response is not None and transaction_response.value:
                # Печать последней транзакции
                transaction = transaction_response.value.transaction
                tx_signature = transaction.transaction.signatures[0]
                cprint(f"Link to transaction in explorer : https://explorer.solana.com/tx/{tx_signature}", "magenta", "on_light_green")



                message = transaction.transaction.message.account_keys
                account_keys = [str(key.pubkey) for key in message]

                pre_balances = transaction.meta.pre_balances
                post_balances = transaction.meta.post_balances

                pre_balance = transaction.meta.pre_token_balances
                post_balance = transaction.meta.post_token_balances
                # cprint(f"pre_balance: \n{pre_balance}", "light_blue")
                # cprint(f"post_balance: \n{post_balance}", "light_green")

                sol = self.from_token if self.from_token == "So11111111111111111111111111111111111111112" else self.to_token
                new_token = self.from_token if self.from_token != "So11111111111111111111111111111111111111112" else self.to_token

                diffs = {sol: 0, new_token: 0}
                for pre in pre_balance:                    
                    for post in post_balance:                       
                        if pre.account_index == post.account_index:                            

                            pre_ui_amount = float(pre.ui_token_amount.ui_amount_string)
                            post_ui_amount = float(post.ui_token_amount.ui_amount_string)
                            decimal = post.ui_token_amount.decimals             
                            diff = round(post_ui_amount - pre_ui_amount, decimal)
                            pre_mint = str(pre.mint)
                            post_mint = str(post.mint)
                            
                            
                            if abs(diff) > 0:
                                print(colored(f"Account index: {pre.account_index} <> {post.account_index}", "light_yellow", attrs=["bold", "reverse"]), 
                                colored(pre_mint, "white", "on_black"), colored(post_mint, "white", "on_black"), 
                                colored(f" amount: {pre_ui_amount} - {post_ui_amount} = {diff}", "cyan"))
                                                
                                if pre_mint == sol:
                                    diffs[sol] = abs(diff)
                                else:
                                    diffs[new_token] = abs(diff)
                cprint(diffs, "magenta", attrs=["bold"])
                
                print()
                try:     
                    current_price = diffs[sol] / diffs[new_token]
                except ZeroDivisionError:
                    current_price = 0
                cprint(f"Current price: {current_price:.14f}", "white", "on_light_blue", attrs=["bold"])
                
                # Создаем список словарей для данных
                data = []
                for i in range(len(account_keys)):
                    data.append({
                        "account_keys": account_keys[i],
                        "pre_balance": pre_balances[i],
                        "post_balance": post_balances[i]
                    })

                # Создаем DataFrame
                df = pd.DataFrame(data)

                # Добавляем колонку с изменением баланса
                df['balance_change'] = df['post_balance'] - df['pre_balance']
                df['balance_change_in_sol'] = df['balance_change'] / 1000000000

                # Печатаем DataFrame
                cost_of_swap_with_fee = df['balance_change_in_sol'][0]
                cprint(f"Стоимость транзакции c коммиссией: {cost_of_swap_with_fee:.9f} SOL", "light_yellow")

                # Сохраняем DataFrame в CSV
                # df.to_csv("transaction_balances.csv", index=False)

                return current_price
        # except Exception as e:
        #     cprint(f"Error while getting price {str(e)}", "red", attrs=["bold", "reverse"])

    def track_pnl(self, bought_price):
        while True:
            try:
                ...
            except Exception as e:
                cprint(f"Error while getting pnl: {str(e)}", "red", attrs=["bold", "reverse"])


if __name__ == "__main__":
    pool_id = Pubkey.from_string("CVu5PkozXP7x2SdhvkkY3EjRoJGhfKkda1sYhHo8jsfv")
    from_token = "So11111111111111111111111111111111111111112" 
    to_token = "7pfftjcqR3tV5wuTdNMrdAVfpC1yqCRwo6cAUPjApump"

    tracker = RaydiumPnLTracker(pool_id, from_token, to_token)
    # tracker.get_current_transaction()
    signature = Signature(base58.b58decode("7nsSaoKRfcxieLEwyb3SAgHYA7YTmZaR11HNUC5puVHy6pGJJRUhdjru73231gucTdb8Ma6tMjMKXrcPCr7CVjN"))
    tracker.get_current_price(signature)


# class RaydiumPoolTracker:
#     def __init__(self, rpc_url="https://api.mainnet-beta.solana.com"):
#         self.client = Client(rpc_url)
#         # Программный ID Raydium AMM
#         self.RAYDIUM_AMM_V4_PROGRAM_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
        
#     def get_pool_state(self, pool_address: str):
#         """
#         Получает состояние пула из смарт-контракта
        
#         Args:
#             pool_address (str): Адрес пула ликвидности
#         Returns:
#             dict: Данные пула
#         """
#         try:
#             pool_pubkey = Pubkey.from_string(pool_address)
#             # Используем get_account_info с правильной обработкой ответа
#             response = self.client.get_account_info(pool_pubkey)

#             try:
#                 pool_state = self.get_pool_state(pool_address)
#                 print(pool_state)
#                 if pool_state:
#                     current_price, _ = self.calculate_price(pool_state)
#                     pnl_percentage = self.calculate_pnl(purchase_price, current_price)
#                     initial_value = purchase_price * tokens_amount
#                     current_value = current_price * tokens_amount
#                     absolute_pnl = current_value - initial_value
                    

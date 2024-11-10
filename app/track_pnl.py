import base58
import time
from solana.rpc.api import Client
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
import pandas as pd
from datetime import datetime

from termcolor import colored, cprint


class RaydiumPnLTracker:
    def __init__(self, pool_id, from_token, to_token, amount=0.01, stop_loss=20, take_profit=30, rpc_url="https://api.mainnet-beta.solana.com"):
        self.client = Client(rpc_url)
        self.pool_id = pool_id
        self.from_token = from_token
        self.to_token = to_token
        self.amount = amount
        self.stop_loss = stop_loss
        self.take_profit = take_profit

    def get_price_for_current_transaction(self):
        # try:
            # Получаем список подписей транзакций для этого пула
            signatures_response = self.client.get_signatures_for_address(self.pool_id)

            # Проверяем, успешен ли запрос
            if signatures_response is not None and signatures_response.value:
                # Получаем подпись последней транзакции
                latest_signature = signatures_response.value[0].signature
            
                price, _, price_with_fee = self.get_current_price(latest_signature)
                return price, price_with_fee
            
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
                # cprint(f"Link to transaction in explorer : https://explorer.solana.com/tx/{tx_signature}", "magenta", "on_light_green")

                pre_balances = transaction.meta.pre_balances
                post_balances = transaction.meta.post_balances
                cost_of_swap_with_fee = (post_balances[0] - pre_balances[0]) / 1000000000
                cprint(f"Стоимость транзакции c коммиссией: {cost_of_swap_with_fee:.9f} SOL", "light_green")

                pre_balance = transaction.meta.pre_token_balances
                post_balance = transaction.meta.post_token_balances
                
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
                                # print(colored(f"Account index: {pre.account_index} <> {post.account_index}", "light_yellow", attrs=["bold", "reverse"]), 
                                # colored(pre_mint, "white", "on_black"), colored(post_mint, "white", "on_black"), 
                                # colored(f" amount: {pre_ui_amount} - {post_ui_amount} = {diff}", "cyan"))
                                                
                                if pre_mint == sol:
                                    diffs[sol] = abs(diff)
                                elif pre_mint == new_token:
                                    diffs[new_token] = abs(diff)
                cprint(diffs, "magenta", attrs=["bold"])
                
                print()
                try:     
                    current_price = diffs[sol] / diffs[new_token]
                except ZeroDivisionError:
                    current_price = 0
                cprint(f"Current price: {current_price:.14f}  =========   Time: {datetime.now().strftime('%d-%m %H:%M:%S')}", "red", "on_light_yellow", attrs=["bold"])

                return current_price, diffs, cost_of_swap_with_fee
        # except Exception as e:
        #     cprint(f"Error while getting price {str(e)}", "red", attrs=["bold", "reverse"])

    def track_pnl(self, bought_price, cost_with_fee):
        while True:
            # try:

                amount_of_new_token = abs(cost_with_fee / bought_price)
                cprint(f"Amount of new token with fee: +{amount_of_new_token:.4f} tokens ", "white", attrs=["bold"])

                current_price, _ = self.get_price_for_current_transaction()
                
                if current_price:
                    pnl = current_price - bought_price
                    pnl_percentage = ((current_price - bought_price) / bought_price) * 100

                    color_pnl = "on_green" if pnl_percentage >= 0 else "on_red"
                    cprint(f"Bought price: {bought_price:.10f}", "white", attrs=["bold"])
                    print(colored("PnL:   ", "yellow", attrs=["bold"]), end="")
                    print(colored(f" {pnl:.14f} ({pnl_percentage:.2f}%)", color_pnl, attrs=["bold"]),
                          colored(f"Time: {datetime.now().strftime('%d-%m %H:%M:%S')}", "white", attrs=["bold"]))
                    if pnl_percentage > self.take_profit:
                        print(colored(f"Take profit {pnl_percentage:.2f}% reached!!!", "green", attrs=["bold"]))
                        return current_price, pnl, pnl_percentage
                    if pnl_percentage < self.stop_loss:
                        print(colored(f"Stop loss {pnl_percentage:.2f}% reached!!!", "red", attrs=["bold"]))
                        return current_price, pnl, pnl_percentage
                time.sleep(30)
            # except Exception as e:
            #     cprint(f"Error while getting pnl: {str(e)}", "red", attrs=["bold", "reverse"])


if __name__ == "__main__":
    print(f"Текущая дата и время: {datetime.now()}")
    pool_id = Pubkey.from_string("35JZmQQC6EWrW6PefWDLhmTXbKvNC9MxpbEs4rBwS1WW")
    from_token = "So11111111111111111111111111111111111111112" 
    to_token = "51zudBR4NmATG35goida4dLQH5YPn9k8hVkLcizNpump"
    tracker = RaydiumPnLTracker(pool_id, from_token, to_token, 0.1)
    # tracker.get_price_for_current_transaction()
    signature = Signature(base58.b58decode("bZKmJ9L3WQU6X3PLmzQmxe6MCygfPMfB6t6w7ksnBiZMmBribwht8ZHAEyEzsVJXrZ7LFmACQ6Wnkc3BoY2cTc9"))
    for i in range(5):        
        start_price, cost_with_fee = tracker.get_price_for_current_transaction()

        if start_price:
            time.sleep(30)
            tracker.track_pnl(start_price, cost_with_fee)
            break
        time.sleep(5)
                    



                # message = transaction.transaction.message.account_keys
                # account_keys = [str(key.pubkey) for key in message]


                # # Создаем список словарей для данных
                # data = []
                # for i in range(len(account_keys)):
                #     data.append({
                #         "account_keys": account_keys[i],
                #         "pre_balance": pre_balances[i],
                #         "post_balance": post_balances[i]
                #     })

                # # Создаем DataFrame
                # df = pd.DataFrame(data)

                # # Добавляем колонку с изменением баланса
                # df['balance_change'] = df['post_balance'] - df['pre_balance']
                # df['balance_change_in_sol'] = df['balance_change'] / 1000000000

                # # Печатаем DataFrame
                # cost_of_swap_with_fee = df['balance_change_in_sol'][0]
                # cprint(f"Стоимость транзакции c коммиссией: {cost_of_swap_with_fee:.9f} SOL", "light_yellow")

                # # Сохраняем DataFrame в CSV
                # # df.to_csv("transaction_balances.csv", index=False)
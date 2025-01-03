
import base58

import logging
import time
import requests

from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
from solana.rpc.api import Client
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Commitment
from solana.rpc.websocket_api import connect, SolanaWsClientProtocol

from decimal import Decimal, InvalidOperation
from termcolor import colored, cprint

from datetime import datetime



class RaydiumPnLTracker:
    def __init__(self, pool_id, from_token, to_token, amount=0.001, rpc_url="https://api.mainnet-beta.solana.com"):
        self.client = Client(rpc_url)
        self.pool_id = pool_id
        self.from_token = from_token
        self.to_token = to_token
        self.amount = amount

    def get_price_for_current_transaction(self):
        
        # try:
            # Получаем список подписей транзакций для этого пула
            signatures_response = self.client.get_signatures_for_address(self.pool_id)

            # Проверяем, успешен ли запрос
            if signatures_response is not None and signatures_response.value:
                # Получаем подпись последней транзакции
                latest_signature = signatures_response.value[0].signature
                price, bought_tokens_amount, cost_of_swap_with_fee, swap_commision = self.get_current_price(latest_signature)
                return price
            
        # except Exception as e:
        #     logging.error(f"Error while getting current transaction: {str(e)}")


    def get_current_price(self, signature: Signature):
        # try:
            # signature = Signature(base58.b58decode(signature))

            # Получаем информацию о последней транзакции по подписи
            transaction_response = self.client.get_transaction(
                signature,
                # encoding="jsonParsed",
                max_supported_transaction_version=0
            )

            # Проверяем, что данные получены
            if transaction_response is not None and transaction_response.value:
                # Печать последней транзакции
                transaction = transaction_response.value.transaction
                # tx_signature = transaction.transaction.signatures[0]
                # with open("swap_transactions.json", 'a', encoding='utf-8') as raw_transactions:
                #     raw_transactions.write(transaction.to_json())
                #     raw_transactions.write(",\n")

                pre_balances = transaction.meta.pre_balances
                post_balances = transaction.meta.post_balances
            
                
                cost_of_swap_with_fee = (post_balances[0] - pre_balances[0]) / 1000000000  # стоимость swap в SOL c коммиссии
                

                pre_balance = transaction.meta.pre_token_balances
                post_balance = transaction.meta.post_token_balances
                
                sol = self.from_token if self.from_token == "So11111111111111111111111111111111111111112" else self.to_token
                new_token = self.from_token if self.from_token != "So11111111111111111111111111111111111111112" else self.to_token

                diffs = {sol: 0, new_token: 0}
                try:
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

                                    if pre_mint == sol:
                                        diffs[sol] = abs(diff)
                                    elif pre_mint == new_token:
                                        diffs[new_token] = abs(diff)
                except Exception as e:
                    # cprint(f"Error while getting diffs: {str(e)}", "red", attrs=["bold", "reverse"])
                    logging.error(f"Error while getting diffs: {str(e)}")

                bought_tokens_amount = diffs[new_token]
                print(f"bought_tokens_amount = {bought_tokens_amount}")
                logging.debug('diffs   ', diffs)
                try:     
                    price = diffs[sol] / diffs[new_token]
                except ZeroDivisionError:
                    price = 0
                
                return (
                    price, 
                    bought_tokens_amount, 
                    cost_of_swap_with_fee
                )
        # except requests.exceptions.Timeout:
        #     cprint("Request timed out, retrying...", "yellow")


if __name__ == "__main__":
    print(f"Текущая дата и время: {datetime.now()}")
    pool_id = Pubkey.from_string("J6TqXv7aKViW9ksWh7p9fAPfGxuKASnEJnm6RZyNfVSN")
    from_token = "So11111111111111111111111111111111111111112" 
    to_token = "GEWtemSg3rXSXZikMStCjq67vEqxTSiNfnL7cTfpump"
    tracker = RaydiumPnLTracker(pool_id, from_token, to_token, 0.1)
    
    signature = Signature(base58.b58decode("4WoqGuLaBjGWYABD2fF1xQXAduEp7KWsZqFYrU4aehpBJ5PCz6Koeo3vErceLe3UzrTDk3dqbKgFE2rhkNeTDn6v"))
    price, _, _ = tracker.get_current_price(signature)
    print(f"price = {price:.10f}")


    # while True: 

    #     if price:
    #         tracker.get_pnl(price, 26760) 
    #         time.sleep(10)
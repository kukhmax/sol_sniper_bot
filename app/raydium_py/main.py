import os
import base58
import requests
import pandas as pd
from solders.keypair import Keypair  #  type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore

from termcolor import colored, cprint
import asyncio
import time
import json
from datetime import datetime

from find_new_token import find_new_tokens
from track_pnl import RaydiumPnLTracker
from raydium import sell, buy
from config import payer_keypair, MAIN_RPC
from global_bot import GlobalBot
from utils import get_token_balance, find_data

from playsound import playsound


class RaydiumSniper:
    def __init__(self, sol_in, slippage, priority_fee, global_bot):
        # Добавляем необязательный параметр global_bot
        self.global_bot = global_bot or GlobalBot.get_instance()

        self.RaydiumLPV4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
        self.payer_pubkey = payer_keypair.pubkey()
        self.mint = None
        self.base = None
        self.pair_address = None
        self.token_name = None
        self.token_symbol = None
        self.sol_in = sol_in
        self.slippage = slippage
        self.priority_fee = priority_fee
        self.tracker = None
        self.token_amount = 0
        self.bought_price:float = 0
        self.sold_price:float = 0
        self.buy_txn_signature = None
        self.sell_txn_signature = None
        self.bought_amount_with_fee = 0
        self.swap_commision = 0
        self.pool_data = []
        self.df = pd.DataFrame(self.pool_data)
    
    async def get_balance(self):
        try:
            pubkey_str = str(self.payer_pubkey)
            headers = {"accept": "application/json", "content-type": "application/json"}

            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "getTokenAccountsByOwner",
                "params": [
                    pubkey_str,
                    {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                    {"encoding": "jsonParsed", "commitment": "confirmed"}
                ],
            }
            
            response = requests.post(MAIN_RPC, json=payload, headers=headers)
            data = response.json()

            tokens = []
            for account in data.get('result', {}).get('value', []):
                info = account['account']['data']['parsed']['info']
                
                # Skip empty or zero balance accounts
                if float(info['tokenAmount']['amount']) == 0:
                    continue
                
                # r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{info['mint']}/report")
                # cprint(f"Status code: {r.status_code} - {r.reason}", "yellow")
                # if r.status_code == 200:                
                #     data = r.json()
                #     token_name = data['tokenMeta']['name']
                #     token_symbol = data['tokenMeta']['symbol']

                token_details = {
                    'mint': info['mint'],
                    # 'name': f"{token_symbol} ({token_name})",
                    'amount': float(info['tokenAmount']['amount']) / (10 ** info['tokenAmount']['decimals']),
                }
                tokens.append(token_details)



            cprint(tokens)
        except Exception as e:
            return None
    

    async def get_new_raydium_pool(self, max_retries, retry_delay):
        for attempt in range(max_retries):
            try:        
                data = await find_new_tokens(self.RaydiumLPV4)
                if data:                    
                    self.base, self.mint, self.pair_address = data
                    return data
            except Exception as e:
                cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
                await asyncio.sleep(retry_delay)
        return False
    
    async def check_if_rug(self, mint_token=None):
        try:
            if not mint_token:
                mint_token = self.mint
            r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{self.mint}/report")
            cprint(f"Status code: {r.status_code} - {r.reason}", "yellow")
            if r.status_code == 200:                
                data = r.json()
                score = data['score']
                cprint(f"Score: {score}", "yellow")
                self.token_name = data['tokenMeta']['name']
                self.token_symbol = data['tokenMeta']['symbol']
                print(colored(data["tokenMeta"]["symbol"], "blue", attrs=["bold"]), end="  ( ")
                print(colored(data["tokenMeta"]["name"], "green", attrs=["bold"]), ")")

                await self.global_bot.send_message(f"""
New token found: {data['tokenMeta']['symbol']} ({data['tokenMeta']['name']})
Score: {score}
                                                   """)
                for risk in data['risks']:
                    cprint(f"{risk['name']} - {risk['level']}", "cyan", "on_white", attrs=["bold"])
                    if_danger = "🛑" if risk['level'] == "danger" else "✅"
                    await self.global_bot.send_message(f"{if_danger} {risk['name']} - {risk['level']}")
                    if risk["name"] == "Freeze Authority still enabled":
                        playsound('app/raydium_py/signals/extra_special.mp3')
                        cprint("Tokens can be frozen and prevented from trading !!!","red", attrs=["bold", "reverse"])
                        return False
                    if risk["level"] == "danger":
                        playsound('app/raydium_py/signals/extra_special.mp3')
                        cprint(f"Risk level: {risk['level']}", "red", attrs=["bold", "reverse"])
                        return False
                return True
        except Exception as e:
            cprint(f"Error in check_if_rug: {str(e)}", "red", attrs=["bold", "reverse"])
            return False
    
    async def buy(self):
        # cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
        confirm = False
        for _ in range(4):
            self.buy_txn_signature, confirm = buy(str(self.pair_address), self.sol_in, self.slippage)
            if confirm:
                return confirm

            await asyncio.sleep(4)
        return False  
        
    async def sell(self, percentage=100):
        try:
            for attempt in range(3):
                confirm, self.sell_txn_signature = sell(str(self.pair_address), percentage)
                if confirm:
                    playsound('app/raydium_py/signals/sell.mp3')
                    
                    await self.global_bot.send_message(f"💹 Token {self.token_symbol} Sold Successfully!!!")
                    return confirm
                await asyncio.sleep(2)
            return False
        except Exception as e:
            cprint(f"Error in sell: {str(e)}", "red", attrs=["bold", "reverse"])
            return False

    async def get_sell_price(self, txn_sgn):
        
        try:
            price_data = self.tracker.get_current_price(self.sell_txn_signature)
            if price_data:
                    self.sold_price, self.token_amount, _, swap_commision = price_data
                    sell_info = f"""
Sell Price: {self.sold_price:.10f} SOL
Token Amount: {self.token_amount} {self.token_symbol}
                            """
                    await self.global_bot.send_message(sell_info)
                    return price_data
        except Exception as e:
            cprint(f"Ошибка при получении цены продажи: {e}", "red", attrs=["bold", "reverse"])
        #         time.sleep(10)
        # cprint(f"Не удалось получить цену продажи", "red", attrs=["bold", "reverse"])

    async def get_bought_price(self):
        while True:
            try:
                self.bought_price, self.token_amount, self.bought_amount_with_fee, self.swap_commision = self.tracker.get_current_price(self.buy_txn_signature)
                if self.bought_price:
                     return
            except Exception as e:
                cprint(f"Ошибка при получении цены покупки: {e}", "red", attrs=["bold", "reverse"])
                time.sleep(4)

        
    async def track_pnl(self, take_profit, stop_loss):
        cprint("tracking PnL...", "green", attrs=["bold"])
        count = 0
        count_0 = 0
        while True:
            try:        
                await asyncio.sleep(5)
                pnl_percentage = self.tracker.get_pnl(
                    self.bought_price,
                    self.token_amount,
                    # self.bought_amount_with_fee,
                    # self.swap_commision
                )
                if pnl_percentage < -90:
                    continue
                if pnl_percentage > take_profit:
                    playsound('app/raydium_py/signals/wow.mp3')
                    print(colored(f"Take profit {pnl_percentage:.2f}% reached!!!", "green", attrs=["bold"]))
                    return
                # if pnl_percentage < stop_loss:
                #     print(colored(f"Stop loss {pnl_percentage:.2f}% reached!!!", "red", attrs=["bold"]))
                #     if count == 1:
                #         playsound('app/raydium_py/signals/cry.mp3')
                #         return
                #     count += 1
                #     continue
                
                # if pnl_percentage == 0:
                #     if count_0 == 5:
                #         print(colored(f"Price not changed for 5 minutes!!!", "red", attrs=["bold", "reverse"]))
                #         return
                #     count_0 += 1
            except Exception as e:
                    cprint(f"Error while tracking PnL: {str(e)}", "red", attrs=["bold", "reverse"])
                    if  "cannot access local variable 'pnl' where it is not associated with a value" in str(e):
                        return
                    # if count == 10:
                    #     return
                    await asyncio.sleep(10)
                    # count += 1
    
    async def run(self):
        
        while True:     

            new_pool = await self.get_new_raydium_pool(5, 2)
            playsound('app/raydium_py/signals/combat_warning.mp3')
            cprint(f"Dexscreener URL with my txn: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
            cprint(f"GMGN SCREENER URL : https://gmgn.ai/sol/token/{self.mint}", "light_magenta")
            await asyncio.sleep(8)

            rugcheck = await self.check_if_rug()            

            if rugcheck and new_pool:
                playsound('app/raydium_py/signals/76a24c7c8089950.mp3')

                token_info = f"""
🚀 Rug checked:
Token: {self.token_symbol} ({self.token_name})
Screener URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}
GMGN URL: https://gmgn.ai/sol/token/{self.mint}
                """

                await self.global_bot.send_message(token_info)

                self.tracker = RaydiumPnLTracker(self.pair_address, self.base, self.mint)
                await asyncio.sleep(2)
                confirm =  await self.buy()
                if confirm:
                    playsound('app/raydium_py/signals/buy.mp3')                      
                    await self.get_bought_price()
                    if self.bought_price:
                        buy_info = f"""       
💹 Token Bought Successfully:
Buy Price: {self.bought_price:.10f} SOL
Token Amount: {self.token_amount} {self.token_symbol}
                        """
                        await self.global_bot.send_message(buy_info)

                        await self.track_pnl(50, -10)
                        
                        while True:
                            token_balance = get_token_balance(str(self.mint))
                            cprint(f"token balance: {token_balance}", "green", attrs=["bold"])
                            if not token_balance:
                                break
                            await asyncio.sleep(5)
                        # sell_confirm = await self.sell()

                        # if sell_confirm:                            
                        #     await asyncio.sleep(2)
                        #     sell_data = await self.get_sell_price(self.sell_txn_signature)
                        #     print(f"sell price: {sell_data[0]}")

                        #     #TODO : если продажа на 100% прошла , self.token_amount = 0 или проверить amount

                        #     print(f"token_name: {self.token_name}")
                        #     print(f"pair_address: {str(self.pair_address)}")
                        #     print(f"base: {str(self.mint)}")
                        #     print(f"mint: {str(self.base)}")
                        #     print(f"link_to_pool: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}")
                        #     # print(f"link_to_buy_txn: https://explorer.solana.com/tx/{self.txn_signature}")
                        #     print(f"buy_price (SOL): {self.bought_price:.10f}")
                        #     print(f"buy_amount_with_fee (SOL): {self.bought_amount_with_fee}")
                        #     print(f"link_to_sell_txn: https://explorer.solana.com/tx/{self.sell_txn_signature}")


                # cprint("Saving swap data to CSV file...", "yellow")

                # self.pool_data.append[{
                #     "token_name": self.token_name,
                #     "pair_address": str(self.pair_address),
                #     "base": str(self.mint),
                #     "mint": str(self.base),
                #     "link_to_pool": f"https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}",
                #     "link_to_buy_txn": f"https://explorer.solana.com/tx/{self.txn_signature}",
                #     "buy_price (SOL)": self.bought_price,
                #     "buy_amount_with_fee (SOL)": self.price_with_fee,
                #     "link_to_sell_txn": f"https://explorer.solana.com/tx/{sell_txn}",
                #     "sell_price": self.sell_price,
                #     # "sell_amount_with_fee (SOL)": sell_price_with_fee
                # }]

                # filename = "app/swap_data.csv"
                # if not os.path.isfile(filename):
                #     self.df.to_csv(filename, index=False)
                # else:
                #     self.df.to_csv(filename, mode='a', header=False, index=False)

        # self.tracker = RaydiumPnLTracker(
        #     "2ZafAX1i8SpG1YE4mvQhqyVRYGijqHTnD6uPYZ9kaqbL",
        #     "Fk2wnisZ4AjWtUfep1NXPjWbEFqUvWDnhXxGcGfopump", 
        #     "So11111111111111111111111111111111111111112", 
        #     )
        # data =await self.get_sell_price(Signature(base58.b58decode("3vaHBbV1mLb943kwJQkVwDGxU7yJYBgPaKQrScdbM44X7jiPWcAuZ3yFXdMvaC6YDZNJAwqE9DjHy1Ek1i6z9uVw")))
        # for i in data:
        #     print(type(i))
        #     print(f"{i:.15f}")


if __name__ == "__main__":
    SOL_IN = 0.03
    SLIPPAGE = 20
    PRIORITY_FEE = 0.00005
    sniper = RaydiumSniper(SOL_IN, SLIPPAGE, PRIORITY_FEE, None)
    asyncio.run(sniper.run())
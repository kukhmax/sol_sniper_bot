import os
import base58
import requests
import pandas as pd
from solders.keypair import Keypair  #  type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
from solana.rpc.async_api import AsyncClient

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
    def __init__(self, sol_in=0.01, slippage=10, priority_fee=0, global_bot=None):
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
            # Mainnet RPC endpoint (replace with your preferred endpoint)
            rpc_url = "https://api.mainnet-beta.solana.com"
            
            # Create an async Solana client
            async with AsyncClient(rpc_url) as client:
                # Get account info
                account_info = await client.get_account_info(self.payer_pubkey )
                
                # Check if account exists
                if account_info.value is None:
                    print(f"Account {self.payer_pubkey} does not exist.")
                    return 0.0
                
                # Get balance in lamports (1 SOL = 10^9 lamports)
                balance_lamports = account_info.value.lamports
                
                # Convert lamports to SOL
                balance_sol = balance_lamports / 10**9
                
                return balance_sol
        
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return 0.0

    async def get_new_raydium_pool(self, max_retries, retry_delay):
        for attempt in range(max_retries):
            try:        
                data = await find_new_tokens(self.RaydiumLPV4)
                if data:                    
                    self.base, self.mint, self.pair_address = data
                    return True
            except Exception as e:
                cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
                await asyncio.sleep(retry_delay)
        return False
    
    async def check_if_rug(self, mint_token=None):
        for _ in range(2):
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
                await asyncio.sleep(40)
            except Exception as e:
                cprint(f"Error in check_if_rug: {str(e)}", "red", attrs=["bold", "reverse"])
                return False
    
    async def buy(self, pair_address=None):
        if not pair_address:
            pair_address = self.pair_address
        # cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
        confirm = False
        for _ in range(4):
            self.buy_txn_signature, confirm = buy(str(pair_address), self.sol_in, self.slippage)
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
        current_pnl = 30
        while True:
            try:        
                await asyncio.sleep(1)
                pnl_percentage = self.tracker.get_pnl(
                    self.bought_price,
                    self.token_amount,
                    # self.bought_amount_with_fee,
                    # self.swap_commision
                )
                if pnl_percentage < -90:
                    continue
                if pnl_percentage > current_pnl + 10:
                    cprint(f"Price changed by {pnl_percentage - current_pnl:.2f}%!!", "green", attrs=["bold"])
                    current_pnl = pnl_percentage

                if pnl_percentage < current_pnl - 50: 
                    cprint(f"Price changed by {pnl_percentage - current_pnl:.2f}%!!", "red", attrs=["bold"])
                    current_pnl = pnl_percentage

                
                if pnl_percentage > take_profit:
                    playsound('app/raydium_py/signals/wow.mp3')
                    print(colored(f"Take profit {pnl_percentage:.2f}% reached!!!", "green", attrs=["bold"]))
                    return 65
                # if pnl_percentage < stop_loss:
                #     print(colored(f"Stop loss {pnl_percentage:.2f}% reached!!!", "red", attrs=["bold"]))
                #     if count == 1:
                #         playsound('app/raydium_py/signals/cry.mp3')
                #         return 100
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
            await asyncio.sleep(7)

            rugcheck = await self.check_if_rug()            

            if rugcheck:
                playsound('app/raydium_py/signals/76a24c7c8089950.mp3')

                token_info = f"""
🚀 Rug checked:
Token: {self.token_symbol} ({self.token_name})
Screener URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}
GMGN URL: https://gmgn.ai/sol/token/{self.mint}
                """

                await self.global_bot.send_message(token_info)

                if new_pool:

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

                            percent = await self.track_pnl(100, -10)
                        
                            sell_confirm = await self.sell(percent)
                            token_balance = get_token_balance(str(self.mint))

                            while True:
                                new_token_balance = get_token_balance(str(self.mint))
                                if new_token_balance > 0 and new_token_balance != token_balance:
                                    cprint(f"token balance: {token_balance}", "green", attrs=["bold"])
                                    token_balance = new_token_balance
                                await self.track_pnl(500, -10)
                                if not token_balance:
                                    break
                                await asyncio.sleep(1)

                            if sell_confirm:                            
                                await asyncio.sleep(2)
                                sell_data = await self.get_sell_price(self.sell_txn_signature)
                                print(f"sell price: {sell_data[0]}")

                                #TODO : если продажа на 100% прошла , self.token_amount = 0 или проверить amount

                                print(f"token_name: {self.token_name}")
                                print(f"pair_address: {str(self.pair_address)}")
                                print(f"base: {str(self.mint)}")
                                print(f"mint: {str(self.base)}")
                                print(f"link_to_pool: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}")
                                # print(f"link_to_buy_txn: https://explorer.solana.com/tx/{self.txn_signature}")
                                print(f"buy_price (SOL): {self.bought_price:.10f}")
                                print(f"buy_amount_with_fee (SOL): {self.bought_amount_with_fee}")
                                print(f"link_to_sell_txn: https://explorer.solana.com/tx/{self.sell_txn_signature}")


              

if __name__ == "__main__":
    SOL_IN = 0.02
    SLIPPAGE = 20
    PRIORITY_FEE = 0.00005
    sniper = RaydiumSniper(SOL_IN, SLIPPAGE, PRIORITY_FEE, None)
    asyncio.run(sniper.run())
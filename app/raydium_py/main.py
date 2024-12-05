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
from config import payer_keypair


class RaydiumSniper:
    def __init__(self, sol_in, slippage, priority_fee):
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
        self.buy_txn_signature = None
        self.sell_txn_signature = None
        self.bought_amount_with_fee = 0
        self.swap_commision = 0
        self.pool_data = []
        self.df = pd.DataFrame(self.pool_data)   

    async def get_new_raydium_pool(self, max_retries, retry_delay):
        for attempt in range(max_retries):
            try:        
                data = await find_new_tokens(self.RaydiumLPV4)
                if data:
                    self.mint, self.base, self.pair_address = data
                    return True
            except Exception as e:
                cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
                await asyncio.sleep(retry_delay)
        return False
    
    async def check_if_rug(self):
        try:
            r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{self.base}/report")
            if r.status_code == 200:                
                data = r.json()
                score = data['score']
                cprint(f"Score: {score}", "yellow")
                self.token_name = data['tokenMeta']['name']
                self.token_symbol = data['tokenMeta']['symbol']
                print(colored(data["tokenMeta"]["symbol"], "blue", attrs=["bold"]), end="  ( ")
                print(colored(data["tokenMeta"]["name"], "green", attrs=["bold"]), ")")
                for risk in data['risks']:
                    cprint(f"{risk['name']} - {risk['level']}", "cyan", "on_white", attrs=["bold"])
                    if risk["name"] == "Freeze Authority still enabled":
                        cprint("Tokens can be frozen and prevented from trading !!!","red", attrs=["bold", "reverse"])
                        return False
                    if risk["level"] == "danger":
                        cprint(f"Risk level: {risk['level']}", "red", attrs=["bold", "reverse"])
                        return False
                return True
        except Exception as e:
            cprint(f"Error in check_if_rug: {str(e)}", "red", attrs=["bold", "reverse"])
            return False
    
    async def buy(self):
        cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
        confirm = False
        for _ in range(2):
            self.buy_txn_signature, confirm = buy(str(self.pair_address), self.sol_in, self.slippage)
            if confirm:
                return confirm

            await asyncio.sleep(4)
        return confirm    
        
    async def sell(self):
        try:
            for attempt in range(3):
                confirm, self.sell_txn_signature = sell(str(self.pair_address))
                if confirm:
                    return self.sell_txn_signature
                await asyncio.sleep(2)
            return 0
        except Exception as e:
            cprint(f"Error in sell: {str(e)}", "red", attrs=["bold", "reverse"])
        cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")

    async def get_sell_price(self, txn_sgn):
        
        try:
            price_data = self.tracker.get_current_price(self.sell_txn_signature)
            if price_data:
                    price, token_amount, amount_with_fee, swap_commision = price_data
                    return price
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
                
                pnl_percentage = self.tracker.get_pnl(
                    self.bought_price,
                    self.token_amount,
                    # self.bought_amount_with_fee,
                    # self.swap_commision
                )
                if pnl_percentage > take_profit:
                    print(colored(f"Take profit {pnl_percentage:.2f}% reached!!!", "green", attrs=["bold"]))
                    return
                if pnl_percentage < stop_loss:
                    print(colored(f"Stop loss {pnl_percentage:.2f}% reached!!!", "red", attrs=["bold"]))
                    if count == 1:
                        return
                    count += 1
                    continue
                await asyncio.sleep(5)
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
            cprint(f"Dexscreener URL with my txn: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
            cprint(f"GMGN SCREENER URL : https://gmgn.ai/sol/token/{self.base}", "light_magenta")
            await asyncio.sleep(5)
            rugcheck = await self.check_if_rug()
            if rugcheck:
            
                if new_pool:
                    self.tracker = RaydiumPnLTracker(self.pair_address, self.mint, self.base)
                    confirm =  await self.buy()
                    cprint(self.buy_txn_signature, "green", attrs=["bold"])
                    if confirm:                        
                        await self.get_bought_price()
                        cprint(f"swap_commision: {self.swap_commision}", "green", attrs=["bold"])
                        if self.bought_price:
                            await self.track_pnl(50, -10)
                            await self.sell()

                            if self.sell_txn_signature:
                                sell_price = await self.get_sell_price(self.sell_txn_signature)
                                print(f"sell price: {sell_price}")

                            print(f"token_name: {self.token_name}")
                            print(f"pair_address: {str(self.pair_address)}")
                            print(f"base: {str(self.mint)}")
                            print(f"mint: {str(self.base)}")
                            print(f"link_to_pool: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}")
                            # print(f"link_to_buy_txn: https://explorer.solana.com/tx/{self.txn_signature}")
                            print(f"buy_price (SOL): {self.bought_price}")
                            print(f"buy_amount_with_fee (SOL): {self.bought_amount_with_fee}")
                            # print(f"link_to_sell_txn: https://explorer.solana.com/tx/{sell_txn}")


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
    sniper = RaydiumSniper(SOL_IN, SLIPPAGE, PRIORITY_FEE)
    asyncio.run(sniper.run())




#############################################################################
 
async def main():
    RaydiumLPV4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
    max_retries = 5
    retry_delay = 2

    while True:    
        for attempt in range(max_retries):
            try:        
                data = await find_new_tokens(RaydiumLPV4)
                if data:
                    mint, base, pair_address = data
                    break
            except Exception as e:
                cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
                await asyncio.sleep(10)       
        

 
        cprint("swapping pair...", "yellow")
        await asyncio.sleep(13)
        confirm = False
        txn_signature = None
        while not confirm:
            txn_signature, confirm = buy(str(pair_address), SOL_IN, SLIPPAGE)
            
            await asyncio.sleep(5)
        print(type(txn_signature))
        

        # cprint(f"Link to transaction in explorer : https://explorer.solana.com/tx/{txn_signature}", "magenta", "on_light_green")
        await asyncio.sleep(20)

        tracker = RaydiumPnLTracker(pair_address, mint, base, SOL_IN)
        while True:
            try:
                bought_price, bought_tokens_amount, cost_with_fee = tracker.get_current_price(txn_signature)
            except Exception as e:
                cprint(f"Error while getting price: {str(e)}", "red", attrs=["bold", "reverse"])
                continue
            if bought_price:
                break
            await asyncio.sleep(5)
        
        while True:
            try:
                cprint("tracking PnL...", "green", attrs=["bold"])
                await asyncio.sleep(10)
                _, _, pnl_percentage = tracker.track_pnl(bought_price, cost_with_fee)
                # txn_signature = await swap(data[2], data[1], data[0], bought_tokens_amount, SLIPPAGE, PRIORITY_FEE)
                with open("pnl.txt", "a") as f:
                    f.write(f"{datetime.now().strftime('%d-%m %H:%M:%S')} - {pnl_percentage:.2f}%  - {txn_signature}\n")
                cprint(f"Transaction URL: https://dexscreener.com/solana/{data[2]}?maker={data[0]}", "yellow", "on_blue")
                break
            except Exception as e:
                        cprint(f"Error while tracking PnL: {str(e)}", "red", attrs=["bold", "reverse"])






    """

    Пример rug check
    {'name': 'Mint Authority still enabled', 'value': '', 'description': 'More tokens can be minted by the owner', 'score': 50000, 'level': 'danger'}
{'name': 'Freeze Authority still enabled', 'value': '', 'description': 'Tokens can be frozen and prevented from trading', 'score': 25000, 'level': 'danger'}
{'name': 'Low Liquidity', 'value': '$0.00', 'description': 'Low amount of liquidity in the token pool', 'score': 6000, 'level': 'danger'}
{'name': 'Low amount of LP Providers', 'value': '', 'description': 'Only a few users are providing liquidity', 'score': 500, 'level': 'warn'}
{'name': 'Mutable metadata', 'value': '', 'description': 'Token metadata can be changed by the owner', 'score': 100, 'level': 'warn'}
Score: 81600
    """
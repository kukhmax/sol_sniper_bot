import os
import base58
import requests
from solders.keypair import Keypair  #  type: ignore
from solders.pubkey import Pubkey  # type: ignore

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
        self.sol_in = sol_in
        self.slippage = slippage
        self.priority_fee = priority_fee
        self.tracker = None
        self.token_amount = 0
        self.bought_price:float = 0
        self.txn_signature = None
        self.price_with_fee = 0

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
    
    async def check_if_rug():
        # TODO rug check
        ...

    async def buy(self):
        await asyncio.sleep(5)
        confirm = False
        while not confirm:
            self.txn_signature, confirm = buy(str(self.pair_address), SOL_IN, SLIPPAGE)
            await asyncio.sleep(5)
        cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")

    async def sell(self):
        confirm = False
        while not confirm:
            confirm, txn_sgn = sell(str(self.pair_address))
            await asyncio.sleep(5)
        cprint(f"Transaction URL: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")

    
    async def get_bought_price(self):
        while True:
            try:
                price_data = self.tracker.get_current_price(self.txn_signature)
                if price_data:
                    self.bought_price, self.token_amount, self.price_with_fee = price_data                
                    break
            except Exception as e:
                cprint(f"Ошибка при получении цены: {e}", "red", attrs=["bold", "reverse"])
                time.sleep(10)

        
    async def track_pnl(self, take_profit, stop_loss):
        cprint("tracking PnL...", "green", attrs=["bold"])
        count = 0
        while True:
            try:
                count = 0              
                await asyncio.sleep(5)
                _, _, pnl_percentage = self.tracker.get_pnl(self.bought_price)
                if pnl_percentage > take_profit:
                    print(colored(f"Take profit {pnl_percentage:.2f}% reached!!!", "green", attrs=["bold"]))
                    return
                if pnl_percentage < stop_loss:
                    print(colored(f"Stop loss {pnl_percentage:.2f}% reached!!!", "red", attrs=["bold"]))
                    return
                if pnl_percentage == 0:
                    if count == 5:
                        print(colored(f"Pricce not changed for 5 minutes!!!", "red", attrs=["bold", "reverse"]))
                        return
                    count += 1
            except Exception as e:
                    cprint(f"Error while tracking PnL: {str(e)}", "red", attrs=["bold", "reverse"])
                    if  "cannot access local variable 'pnl' where it is not associated with a value" in str(e):
                        return
                    if count == 10:
                        return
                    await asyncio.sleep(10)
                    count += 1


    
    async def run(self):
        while True:
            new_pool = await self.get_new_raydium_pool(5, 2)
            if new_pool:
                self.tracker = RaydiumPnLTracker(self.pair_address, self.mint, self.base)
                await self.buy()
                if self.txn_signature:
                    await self.get_bought_price()
            if self.bought_price:
                await self.track_pnl(100, -30)
                await self.sell()


if __name__ == "__main__":
    SOL_IN = 0.001
    SLIPPAGE = 10
    PRIORITY_FEE = 0.00005
    sniper = RaydiumSniper(SOL_IN, SLIPPAGE, PRIORITY_FEE)
    asyncio.run(sniper.run())





 
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







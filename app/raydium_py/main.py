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


RaydiumLPV4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SECRET_KEY = os.getenv("PRIVATE_KEY")
SOL_IN = 0.002
SLIPPAGE = 10
PRIORITY_FEE = 0.00005


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
        

        # mint, base, pair_address = "So11111111111111111111111111111111111111112", "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", "FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo"
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


if __name__ == "__main__":
    asyncio.run(main())







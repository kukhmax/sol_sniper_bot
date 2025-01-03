import requests
import pandas as pd
import logging
from solders.keypair import Keypair  #  type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.signature import Signature  # type: ignore
from solana.rpc.async_api import AsyncClient

from termcolor import colored, cprint
import asyncio
import time
import json
from datetime import datetime

from app.find_new_token import find_new_tokens
from app.track_pnl import RaydiumPnLTracker
from app.raydium import sell, buy
from app.config import payer_keypair, MAIN_RPC
from app.global_bot import GlobalBot
from app.utils import get_token_balance as gtb, find_data

# from playsound import playsound


# logging.basicConfig(
# #    filename='logs/telegam_bot.log',
# #    filemode='a',
#     level=logging.DEBUG, 
#     format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
#     )

class RaydiumSniper:
    def __init__(self, sol_in, slippage, priority_fee, global_bot=None):
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
        self.is_tracking_pnl = True
        self.pnl_percentage = 0

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
        print("\n")
        logging.info("Getting new Raydium pool...")
        cprint("Getting new Raydium pool...", "green", attrs=["bold", "reverse"])
        for attempt in range(max_retries):
            try:
                data = await find_new_tokens(self.RaydiumLPV4)
                if data:
                    self.base, self.mint, self.pair_address = data
                    return data
            except Exception as e:
                cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}")
                await asyncio.sleep(retry_delay)
        return False

    async def check_if_rug(self, mint_token=None):

        link_to_token = f"https://dexscreener.com/solana/{self.pair_address}"
        link_to_rugcheck = f"https://rugcheck.xyz/tokens/{self.mint}"

        for i in range(2):
            if i == 1:
                await asyncio.sleep(40)
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

                    print(f'{data["tokenMeta"]["symbol"]} ({data["tokenMeta"]["name"]})')

#                    await self.global_bot.send_message(f"""
# ✔️**New token**: [{data['tokenMeta']['symbol']} ({data['tokenMeta']['name']})]({link_to_token})
# 📊**Score**: [{score}]({link_to_rugcheck})""")
                    dangers = []
                    for risk in data['risks']:

                        logging.debug(f"{risk['name']} - {risk['level']}")
                        if risk["name"] == "Freeze Authority still enabled":
                            cprint("Tokens can be frozen and prevented from trading !!!","red", attrs=["bold", "reverse"])
                            return False
                        if risk["level"] == "danger":
                            dangers.append(f"{risk['name']}")

                    if "Low Liquidity" in dangers and len(dangers) == 1:
                        await self.global_bot.send_message(f"🔴 Risks 🔴: {dangers}🔴")
                        return True
                    return True

            except Exception as e:

                cprint(f"Error in check_if_rug: {str(e)}")
                return False

#         await self.global_bot.send_message(f"""
# ⚠️ New token: [⚠️]({link_to_token})
# 📈Score: [{score}]({link_to_rugcheck})""")
        return False

    async def buy(self, pair_address=None):
        print("Buying token...")
        confirm = False
        for _ in range(4):
            self.buy_txn_signature, confirm = buy(str(self.pair_address), self.sol_in, self.slippage)
            if confirm:
                return confirm

            await asyncio.sleep(4)
        return False

    async def sell(self, percentage=100):
        logging.info("Selling token...")
        print("Selling token...")
        try:
            for attempt in range(3):
                confirm, self.sell_txn_signature, sold_token_amount = sell(str(self.pair_address), percentage)
                if confirm:
#                    self.token_amount = gtb(str(self.mint))

                    await self.global_bot.send_message(f"""
💹 Token {self.token_symbol} Sold Successfully!!!
Rest amount: {self.token_amount - sold_token_amount} {self.token_symbol}
                    """)
                    print(f"Token {self.token_symbol} sold successfully!!! Rest amount: {self.token_amount - sold_token_amount} {self.token_symbol}")
                    self.token_amount -= sold_token_amount
                    return confirm
                await asyncio.sleep(2)
            return False
        except Exception as e:
            logging.error(f"Error in sell: {str(e)}")
            cprint(f"Error in sell: {str(e)}", "red", attrs=["bold", "reverse"])
            return False

    async def get_sell_price(self, txn_sgn=None):
        print("Getting sell price...")
        try:
            price_data = self.tracker.get_current_price(self.sell_txn_signature)
            if price_data:
                    self.sold_price, _, _, swap_commision = price_data
                    sell_info = f"""
Sell Price: {self.sold_price:.10f} SOL
Token Amount: {self.token_amount} {self.token_symbol}
                            """
                    await self.global_bot.send_message(sell_info)
                    print(sell_info)
                    return price_data
        except Exception as e:
            cprint(f"Ошибка при получении цены продажи: {e}", "red", attrs=["bold", "reverse"])

    async def get_bought_price(self):
        logging.info("Getting buy price...")
        while True:
            try:
                self.bought_price, self.token_amount, self.bought_amount_with_fee, self.swap_commision = self.tracker.get_current_price(self.buy_txn_signature)
                if self.bought_price:
                     return
            except Exception as e:
                cprint(f"Ошибка при получении цены покупки: {e}")
                time.sleep(3)

    async def track_pnl_and_sell(self, first_tp, second_tp, sp=None):
        cprint("tracking PnL...", "green", attrs=["bold"])
        logging.info("\nTracking PnL...")
        last_pnl = 0
        err_amount = 0
        while self.is_tracking_pnl:
            try:
                await asyncio.sleep(4.5)
                pnl_percentage = self.tracker.get_pnl(
                    self.bought_price
                )
                self.pnl_percentage = pnl_percentage

                if self.token_amount < 1:
                    cprint("Token amount {self.token_amount} is less than 1!!!")
                    await self.global_bot.send_message(f"""
Token amount {self.token_amount} is less than 1!!!
  🔵🟡🔴     Check on wallet!    🔴🟡🔵
                    """)
#                    self.is_tracking_pnl = False
#                    return True

                if pnl_percentage < -90:
                    continue
                if pnl_percentage > 3000:
                    continue
                color_pnl = "🟢" if pnl_percentage > 0 else "🔴"
                if pnl_percentage > last_pnl + 20:
                    cprint(f"Price changed by {pnl_percentage - last_pnl:.2f}%!!!")
                    cprint(f"Current PnL: {pnl_percentage:.2f} /// Token amount: {self.token_amount}")
                    await self.global_bot.send_message(f"""
💹 Token {self.token_symbol}. 🟢  Price changed by {pnl_percentage - last_pnl:.2f}%!!!
{color_pnl}  Current PnL: {pnl_percentage:.2f}  {color_pnl}
Amount: {self.token_amount} {self.token_symbol}
                    """)
                    last_pnl = pnl_percentage

                if pnl_percentage < last_pnl - 20:
                    cprint(f"Price changed by {pnl_percentage - last_pnl:.2f}%!!!")
                    cprint(f"Current PnL: {pnl_percentage:.2f}  /// Token amount: {self.token_amount}")
                    await self.global_bot.send_message(f"""
💹 Token {self.token_symbol}. 🔴  Price changed by {pnl_percentage - last_pnl:.2f}%!!!
{color_pnl}  Current PnL: {pnl_percentage:.2f}  {color_pnl}
Amount: {self.token_amount} {self.token_symbol}
                    """)
                    last_pnl = pnl_percentage

                if pnl_percentage >= second_tp:
                    await self.sell(100)
                    await asyncio.sleep(3)
                    cprint(f"Rest of amount: {self.token_amount}", "magenta", attrs=["bold"])
                    await self.global_bot.send_message(f"Rest of amount {self.token_amount}")
                    self.is_tracking_pnl = False
                    return True
                elif self.pnl_percentage > first_tp:
                    cprint(f"Take profit : {first_tp}", "cyan", attrs=["bold"])
                    await self.sell(60)
                    await asyncio.sleep(3)
                    await self.global_bot.send_message(f"Rest of amount {self.token_amount}")
                    cprint(f"Rest of amount {self.token_amount}", "magenta", attrs=["bold"])
                    sp = first_tp / 3
                    first_tp += 80
                if sp and self.pnl_percentage <= sp:
                    await self.sell(100)
                    await asyncio.sleep(3)
                    await self.global_bot.send_message(f"Rest of amount {self.token_amount}")
                    cprint(f"Rest of amount {self.token_amount}", "magenta", attrs=["bold"])
                    self.is_tracking_pnl = False
                    return True  


            except Exception as e:
                    cprint(f"Error while tracking PnL: {str(e)}", "red", attrs=["bold", "reverse"])
                    if  "cannot access local variable 'pnl' where it is not associated with a value" in str(e):
                        logging.error("cannot access local variable 'pnl' where it is not associated with a value")

    async def run(self):

        while True:

            new_pool = await self.get_new_raydium_pool(5, 2)

            cprint(f"Dexscreener URL with my txn: https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey}", "yellow", "on_blue")
            cprint(f"GMGN SCREENER URL : https://gmgn.ai/sol/token/{self.mint}", "light_magenta")
            await asyncio.sleep(7)

            rugcheck = await self.check_if_rug()

            if rugcheck and new_pool:
                token_info = f"""
🚀 [Rug checked!!!](https://rugcheck.xyz/tokens/{self.mint})
💼 Token: {self.token_symbol} ({self.token_name})
[Dexscreener](https://dexscreener.com/solana/{self.pair_address}?maker={self.payer_pubkey})🔹[GMGN](https://gmgn.ai/sol/token/{self.mint})🔹[Birdeye](https://www.birdeye.so/token/{self.mint}?chain=solana)
                """

                await self.global_bot.send_message(token_info)

                print(token_info)

                self.tracker = RaydiumPnLTracker(self.pair_address, self.base, self.mint)
                await asyncio.sleep(2)
                confirm =  await self.buy()
                if not confirm:
                    not_confirmed = f"Failed to buy token: {self.token_symbol}"
                    print(not_confirmed)
                    await self.global_bot.send_message(f"❌ {not_confirmed} ❌")
                elif confirm:
                    await self.get_bought_price()
                    if self.bought_price:
                        buy_info = f"""
    💹 Token Bought Successfully:
    Buy Price: {self.bought_price:.10f} SOL
    Token Amount: {self.token_amount} {self.token_symbol}
                        """
                        await self.global_bot.send_message(buy_info)
                        print(buy_info)

                        sell_confirm = await self.track_pnl_and_sell(70, 300)

                        if sell_confirm:
                            print("Sell transaction confirmed")
            else:
                continue

if __name__ == "__main__":
    SOL_IN = 0.03
    SLIPPAGE = 20
    PRIORITY_FEE = 0.00005
    sniper = RaydiumSniper(SOL_IN, SLIPPAGE, PRIORITY_FEE, None)
    asyncio.run(sniper.run())
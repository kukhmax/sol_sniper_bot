import asyncio
import logging
from termcolor import colored, cprint
from playsound import playsound
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from global_bot import GlobalBot
from track_pnl import RaydiumPnLTracker

class TokenTradingManager:
    def __init__(self, sniper, global_bot=None):

        # Добавляем необязательный параметр global_bot
        self.global_bot = global_bot or GlobalBot.get_instance()

        self.sniper = sniper
        self.active_trades = {}
        self.trade_lock = asyncio.Lock()

    async def add_trade(self, token_data: dict):
        async with self.trade_lock:
            trade_id = token_data['mint']
            self.active_trades[trade_id] = token_data
            
            # Создаем инлайн-клавиатуру
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📊 Check PnL", callback_data=f"pnl_{trade_id}"),
                    InlineKeyboardButton(text="💸 Sell 50%", callback_data=f"sell_50_{trade_id}")
                ],
                [
                    InlineKeyboardButton(text="💸 Sell 100%", callback_data=f"sell_100_{trade_id}"),
                    InlineKeyboardButton(text="🔗 View on DEXScreener", 
                                         url=f"https://dexscreener.com/solana/{token_data['pair_address']}?maker={self.sniper.payer_pubkey}")
                ]
            ])
            
            # Отправляем сообщение с инлайн-кнопками
            # global_bot = self.sniper.global_bot
            trade_message = f"""
🚀 New Token Trade Activated:
🛎 Token: {token_data['token_symbol']} ({token_data['token_name']})
📉 Amount: {token_data['token_amount']} 
📜 Pair Address: {token_data['pair_address']}
🟩 Mint: {token_data['mint']}
📈Buy Price: {token_data['bought_price']:.10f} SOL
            """
            await self.global_bot.send_message(trade_message)

    async def handle_callback(self, callback_query):
        """
        Обработчик колбэков от инлайн-кнопок
        """
        data = callback_query.data
        trade_id = data.split('_')[1]
        action = data.split('_')[0]

        trade = self.active_trades.get(trade_id)
        if not trade:
            await callback_query.answer("Trade not found!")
            return

        global_bot = self.sniper.global_bot

        if action == 'pnl':
            # Расчет и отправка PnL
            try:
                tracker = self.sniper.tracker
                pnl_percentage = tracker.get_pnl(
                    trade['bought_price'], 
                    trade['token_amount']
                )
                await global_bot.send_message(
                    f"📊 Current PnL for {trade['token_symbol']}: {pnl_percentage:.2f}%"
                )
                await callback_query.answer()
            except Exception as e:
                await callback_query.answer(f"Error calculating PnL: {str(e)}")

        elif action == 'sell':
            percentage = int(data.split('_')[1])
            try:
                sell_result = await self.sell_trade(trade_id, percentage)
                if sell_result:
                    await callback_query.answer(f"Sold {percentage}% of {trade['token_symbol']}")
                else:
                    await callback_query.answer("Sell transaction failed")
            except Exception as e:
                await callback_query.answer(f"Error selling: {str(e)}")

    async def track_trade_pnl(self, trade_id, take_profit=100, stop_loss=-10):
        try:
            trade = self.active_trades.get(trade_id)
            if not trade:
                cprint(f"No active trade found for {trade_id}", "red")
                return

            tracker = self.sniper.tracker
            bought_price = trade['bought_price']
            token_amount = trade['token_amount']

            while trade_id in self.active_trades:
                try:
                    pnl_percentage = tracker.get_pnl(bought_price, token_amount)
                    
                    # Optional: Send periodic PnL updates
                    global_bot = self.sniper.global_bot
                    await global_bot.send_message(f"📊 Current PnL for {trade['token_symbol']}: {pnl_percentage:.2f}%")

                    if pnl_percentage > take_profit:
                        cprint(f"Take profit reached for {trade['token_symbol']}: {pnl_percentage:.2f}%", "green")
                        await self.sell_trade(trade_id, percentage=65)
                        break

                    if pnl_percentage < stop_loss:
                        cprint(f"Stop loss reached for {trade['token_symbol']}: {pnl_percentage:.2f}%", "red")
                        await self.sell_trade(trade_id, percentage=100)
                        break

                    await asyncio.sleep(5)  # Check PnL every 5 seconds
                except Exception as e:
                    cprint(f"Error tracking PnL for {trade_id}: {e}", "red")
                    break
        except Exception as e:
            cprint(f"Unexpected error in track_trade_pnl: {e}", "red")

    async def sell_trade(self, trade_id, percentage=100):
        async with self.trade_lock:
            trade = self.active_trades.get(trade_id)
            if not trade:
                cprint(f"No active trade found for {trade_id}", "red")
                return False

            try:
                # Use the sniper's sell method
                self.sniper.pair_address = trade['pair_address']
                self.sniper.token_symbol = trade['token_symbol']
                self.sniper.token_name = trade['token_name']
                
                sell_result = await self.sniper.sell(percentage)
                
                if sell_result:
                    # Remove trade after successful sell
                    del self.active_trades[trade_id]
                    
                    global_bot = self.sniper.global_bot
                    await global_bot.send_message(f"💸 Sold {percentage}% of {trade['token_symbol']} successfully")
                    
                    return True
                return False
            except Exception as e:
                cprint(f"Error selling trade {trade_id}: {e}", "red")
                return False

    async def run_trading_cycle(self):
        while True:
            try:
                # Find new token pool
                new_pool = await self.sniper.get_new_raydium_pool(5, 2)
                playsound('app/raydium_py/signals/combat_warning.mp3')
                cprint(f"Dexscreener URL with my txn: https://dexscreener.com/solana/{self.sniper.pair_address}?maker={self.sniper.payer_pubkey}", "yellow", "on_blue")
                cprint(f"GMGN SCREENER URL : https://gmgn.ai/sol/token/{self.sniper.mint}", "light_magenta")
                await asyncio.sleep(6)
                    
                # Check if token is safe
                rugcheck = await self.sniper.check_if_rug()
                
                if rugcheck:
                    playsound('app/raydium_py/signals/76a24c7c8089950.mp3')
                    # Buy the token
                    confirm = await self.sniper.buy()
                    
                    if confirm:
                        playsound('app/raydium_py/signals/buy.mp3')

                        self.sniper.tracker = RaydiumPnLTracker(self.sniper.pair_address, 
                                                                self.sniper.base,
                                                                self.sniper.mint)
                        # Get bought price and token details
                        await self.sniper.get_bought_price()
                        
                        # Prepare trade data
                        trade_data = {
                            'token_symbol': self.sniper.token_symbol,
                            'token_name': self.sniper.token_name,
                            'token_amount': self.sniper.token_amount,
                            'pair_address': str(self.sniper.pair_address),
                            'mint': str(self.sniper.mint),
                            'bought_price': self.sniper.bought_price
                        }
                        
                        
                        # Add trade and start tracking
                        await self.add_trade(trade_data)

                      
                        # Start PnL tracking in background
                        asyncio.create_task(
                            self.track_trade_pnl(trade_data['mint'])
                        )
                
            except Exception as e:
                cprint(f"Error in trading cycle: {e}", "red")
                await asyncio.sleep(10)

    def start(self):
        # Create and run the main trading cycle
        return asyncio.create_task(self.run_trading_cycle())    

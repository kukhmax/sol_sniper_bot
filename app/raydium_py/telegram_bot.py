import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import sys
import threading

# Import the RaydiumSniper class from main.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import RaydiumSniper

# Configure logging
def setup_logging():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
        handlers=[
            logging.FileHandler("telegram_bot.log"),
            logging.StreamHandler()
        ]
    )


class RaydiumTelegramBot:
    def __init__(self, bot_token):
        # Bot configuration
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        
        # Raydium Sniper configuration
        self.sol_in = 0.033
        self.slippage = 10
        self.priority_fee = 0.00005
        
        self.sniper = None  # Инициализируем как None
        self.is_sniper_active = False  # Флаг активности снайпера

        # Trading state
        self.current_token = None
        self.bought_price = None
        self.pnl = None
        
        # Setup handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.dp.message(CommandStart())
        async def cmd_start(message: types.Message):
            keyboard = ReplyKeyboardMarkup(keyboard=[
                [
                    KeyboardButton(text="🎯 Start Sniper 🎯"),
                ],
                [
                    KeyboardButton(text="🔍 Find New Token"),
                    KeyboardButton(text="💰 Check Solana Balance")
                ],
                [
                    KeyboardButton(text="🛒 Buy 100%"),
                    KeyboardButton(text="💸 Sell 50%"),
                    KeyboardButton(text="💸 Sell 100%")
                ],
                [
                    KeyboardButton(text="📊 Current PnL")
                ]
            ], resize_keyboard=True)
            
            await message.answer("Welcome to Raydium Sniper Bot!", reply_markup=keyboard)
        
        @self.dp.message()
        async def handle_messages(message: types.Message):
            if message.text == "🎯 Start Sniper 🎯":
                await self.start_sniper(message)
            elif message.text == "🔍 Find New Token":
                await self.find_new_token(message)
            elif message.text == "💰 Check Solana Balance":
                await self.check_solana_balance(message)
            elif message.text == "🛒 Buy 100%":
                await self.buy_token(message)
            elif message.text == "💸 Sell 50%":
                await self.sell_token(message, percentage=50)
            elif message.text == "💸 Sell 100%":
                await self.sell_token(message, percentage=100)
            elif message.text == "📊 Current PnL":
                await self.show_current_pnl(message)
    
    async def start_sniper(self, message: types.Message):
        if not self.is_sniper_active:
            # Создаем новый экземпляр RaydiumSniper
            self.sniper = RaydiumSniper(self.sol_in, self.slippage, self.priority_fee)
            
            # Запускаем снайпер в отдельном потоке
            def run_sniper():
                asyncio.run(self.sniper.run())
            
            sniper_thread = threading.Thread(target=run_sniper, daemon=True)
            sniper_thread.start()
            
            self.is_sniper_active = True
            await message.answer("🚀 Sniper Bot Started Successfully!")
        else:
            await message.answer("⚠️ Sniper Bot is already running!")
    
    async def find_new_token(self, message: types.Message):
        try:
            # Run the new token finding logic from main.py
            await self.sniper.get_new_raydium_pool(5, 2)
            
            # Check if token is safe
            is_safe = await self.sniper.check_if_rug()
            
            if is_safe:
                token_info = f"""
🚀 New Token Found:
Token Name: {self.sniper.token_name}
Token Symbol: {self.sniper.token_symbol}
Pair Address: {self.sniper.pair_address}
Base Token: {self.sniper.base}
Mint: {self.sniper.mint}
Screener URL: https://dexscreener.com/solana/{self.sniper.pair_address}
                """
                await message.answer(token_info)
                self.current_token = self.sniper.base
            else:
                await message.answer("❌ Unsafe token found. Skipping.")
        except Exception as e:
            await message.answer(f"Error finding token: {str(e)}")
    
    async def check_solana_balance(self, message: types.Message):
        # Placeholder for Solana balance check
        await message.answer("Solana balance check not implemented")
    
    async def buy_token(self, message: types.Message):
        if not self.current_token:
            await message.answer("No token selected. Find a token first!")
            return
        
        try:
            confirm = await self.sniper.buy()
            if confirm:
                await self.sniper.get_bought_price()
                self.bought_price = self.sniper.bought_price
                
                buy_info = f"""
💹 Token Bought Successfully:
Token: {self.sniper.token_name}
Buy Price: {self.bought_price} SOL
Token Amount: {self.sniper.token_amount}
                """
                await message.answer(buy_info)
                
                # Start tracking PnL in background
                asyncio.create_task(self.track_pnl())
            else:
                await message.answer("❌ Buy transaction failed")
        except Exception as e:
            await message.answer(f"Error buying token: {str(e)}")
    
    async def sell_token(self, message: types.Message, percentage: int = 100):
        if not self.current_token:
            await message.answer("No token selected or not bought yet!")
            return
        
        try:
            sell_signature = await self.sniper.sell()
            if sell_signature:
                await message.answer(f"✅ Sold {percentage}% of tokens successfully")
            else:
                await message.answer("❌ Sell transaction failed")
        except Exception as e:
            await message.answer(f"Error selling token: {str(e)}")
    
    async def track_pnl(self):
        try:
            await self.sniper.track_pnl(take_profit=100, stop_loss=-10)
        except Exception as e:
            logging.error(f"PnL tracking error: {str(e)}")
    
    async def show_current_pnl(self, message: types.Message):
        if not self.bought_price:
            await message.answer("No active trade to show PnL")
            return
        
        try:
            pnl_percentage = self.sniper.tracker.get_pnl(
                self.bought_price,
                self.sniper.token_amount
            )
            pnl_message = f"📊 Current PnL: {pnl_percentage:.2f}%"
            await message.answer(pnl_message)
        except Exception as e:
            await message.answer(f"Error calculating PnL: {str(e)}")
    
    def start(self):        
        # Run the Telegram bot
        asyncio.run(self.dp.start_polling(self.bot))

# Usage
if __name__ == "__main__":
    # BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
    BOT_TOKEN = "7475229862:AAHaXp3lcOwp6WDUvlwYQH9vI7RcvDHrxdk"
    raydium_bot = RaydiumTelegramBot(BOT_TOKEN)
    raydium_bot.start()
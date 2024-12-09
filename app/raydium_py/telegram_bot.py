import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import sys
import threading
from termcolor import colored, cprint
from global_bot import GlobalBot

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

        # Новые атрибуты для chat_id
        self.chat_id = 199222002
        global_bot = GlobalBot.get_instance()
        global_bot.set_bot(self.bot, self.chat_id)
        
        # Setup handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.dp.message(CommandStart())
        async def cmd_start(message: types.Message):
            keyboard = ReplyKeyboardMarkup(keyboard=[
                [
                    KeyboardButton(text="🆔 Get Chat ID")    # Новая кнопка
                ],
                [
                    KeyboardButton(text="🎯 Start Sniper 🎯"),
                ],
                [
                    KeyboardButton(text="🔍 Find New Token"),
                    KeyboardButton(text="💰 Check Solana Balance")
                ],
                [
                    # KeyboardButton(text="🛒 Buy 100%"),
                    KeyboardButton(text="💸 Sell 50%"),
                    KeyboardButton(text="💸 Sell 100%")
                ],
                [
                    KeyboardButton(text="📊 Current PnL"),
                    KeyboardButton(text="🛑 Stop Sniper 🛑")

                ]
            ], resize_keyboard=True)
            
            await message.answer("Welcome to Raydium Sniper Bot!", reply_markup=keyboard)
        
        @self.dp.message()
        async def handle_messages(message: types.Message):
            if message.text == "🆔 Get Chat ID":
                await self.get_chat_id(message)
            elif message.text == "🎯 Start Sniper 🎯":
                await self.start_sniper(message)            
            elif message.text == "🔍 Find New Token":
                await self.find_new_token(message)
            elif message.text == "💰 Check Solana Balance":
                await self.check_solana_balance(message)
            elif message.text == "🛒 Buy 100%":
                await self.buy_token(message)
            elif message.text == "💸 Sell 50%":
                await self.sell_token(message, percentage=55)
            elif message.text == "💸 Sell 100%":
                await self.sell_token(message, percentage=100)
            elif message.text == "📊 Current PnL":
                await self.show_current_pnl(message)
            elif message.text == "🛑 Stop Sniper 🛑":
                await self.stop_sniper(message)
    
    async def get_chat_id(self, message: types.Message):
        # Получаем ID чата
        chat_id = message.chat.id
        user_id = message.from_user.id
        username = message.from_user.username
        full_name = message.from_user.full_name
        
        # Сохраняем chat_id в экземпляре класса
        self.chat_id = chat_id
        
        # Формируем информативное сообщение
        info_message = f"""
🆔 Информация о чате:
Chat ID: {chat_id}
User ID: {user_id}
Username: @{username}
Full Name: {full_name}

✅ Chat ID сохранен для использования в боте!
        """

        global_bot = GlobalBot.get_instance()
        global_bot.set_bot(self.bot, chat_id) 
        
        await message.answer(info_message)
        
    
    async def start_sniper(self, message: types.Message):
        if not self.chat_id:
            await message.answer("❗ Сначала получите Chat ID через кнопку 🆔 Get Chat ID")
            return

        if not self.is_sniper_active:
            # Запускаем снайпер в том же event loop, что и Telegram-бот
            self.sniper = RaydiumSniper(
                sol_in=self.sol_in,
                slippage=self.slippage,
                priority_fee=self.priority_fee,
                global_bot=GlobalBot.get_instance()
            )
            self.sniper_task = asyncio.create_task(self.sniper.run())  # Создаем задачу для снайпера
            self.is_sniper_active = True
            await message.answer("🚀 Sniper Bot Started Successfully!")
        else:
            await message.answer("⚠️ Sniper Bot is already running!")

    async def stop_sniper(self, message: types.Message):
        if self.is_sniper_active and self.sniper_task:
            self.sniper_task.cancel()  # Завершаем задачу
            self.sniper_task = None
            self.is_sniper_active = False
            await message.answer("🛑 Sniper Bot Stopped!")
            cprint("==================== Sniper Bot stopped ====================", "red", attrs=["bold", "reverse"])
        else:
            await message.answer("❗ Sniper Bot is not running!")

    
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
        balance = await self.sniper.get_balance()
        # Placeholder for Solana balance check
        await message.answer(f"💰 Solana Balance: {balance} SOL")
    
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
            self.current_token = self.sniper.mint
            # await message.answer("No token selected or not bought yet!")
            # return
        
        try:
            sell_signature = await self.sniper.sell(percentage)
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
        self.bought_price = self.sniper.bought_price
        cprint(f"self.bought_price = {self.bought_price}")
        if not self.bought_price:
            await message.answer("No active trade to show PnL")
            return
        
        try:
            pnl_percentage = self.sniper.tracker.get_pnl(
                self.sniper.bought_price,
                self.sniper.token_amount
            )
            pnl_message = f"📊 Current PnL: {pnl_percentage:.2f}%"
            await message.answer(pnl_message)
        except Exception as e:
            await message.answer(f"Error calculating PnL: {str(e)}")
    
    def start(self):
        global_bot = GlobalBot.get_instance()
        global_bot.set_bot(self.bot, self.chat_id)

        async def run_bot():
            # Запускаем Telegram-бот
            await self.dp.start_polling(self.bot)

        try:
            asyncio.run(run_bot())
        except Exception as e:
            logging.error(f"Error running bot: {e}")


# Usage
if __name__ == "__main__":
    # BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
    BOT_TOKEN = "7475229862:AAHaXp3lcOwp6WDUvlwYQH9vI7RcvDHrxdk"
    raydium_bot = RaydiumTelegramBot(BOT_TOKEN)
    raydium_bot.start()
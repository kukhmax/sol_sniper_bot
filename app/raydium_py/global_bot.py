import logging
import asyncio

class GlobalBot:
    _instance = None

    def __init__(self):
        self.bot = None
        self.chat_id = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = GlobalBot()
        return cls._instance

    def set_bot(self, bot, chat_id):
        """Устанавливает экземпляр бота и chat_id"""
        self.bot = bot
        self.chat_id = chat_id

    async def send_message(self, message):
        """Асинхронно отправляет сообщение через Telegram бот"""
        if not self.bot or not self.chat_id:
            logging.warning("Bot или chat_id не установлен. Сообщение не отправлено.")
            return None

        try:
            logging.info(f"Отправка сообщения: {message}")
            await self.bot.send_message(self.chat_id, message)
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения: {e}")

import os
import asyncio
import json
import logging
from datetime import datetime
from telethon import TelegramClient, events

from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
    filename='telegram_bot.log'
)
logger = logging.getLogger(__name__)

# Безопасное получение credentials из переменных окружения
API_ID = os.getenv('API_ID')  # Получите на https://my.telegram.org/apps
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
SOURCE_CHANNEL = os.getenv('SOURCE_CHANNEL', '@solearlytrending')
TARGET_CHAT_ID = os.getenv('TARGET_CHAT_ID', '199222002')
PHONE_NUMBER = ""

# ID чатов
SOURCE_CHAT_ID = -1002093384030
TARGET_CHAT_ID = 7475229862

# Папка для хранения JSON-файлов
OUTPUT_FOLDER = 'telegram_messages'

# Создаем папку для хранения сообщений, если она не существует
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def parse_message(message):
    """
    Парсит сообщение и возвращает словарь с его деталями
    """
    parsed_message = {
        'id': message.id,
        'date': message.date.isoformat() if message.date else None,
        'text': message.text or '',
        'sender_id': message.sender_id,
        'media': bool(message.media),
        'media_type': str(message.media.__class__.__name__) if message.media else None,
        'forward_from': message.forward.from_id if message.forward else None,
        'forward_date': message.forward.date.isoformat() if message.forward and message.forward.date else None
    }

    # Если есть медиафайл, добавляем информацию о нем
    if message.media:
        try:
            parsed_message['media_details'] = {
                'file_name': getattr(message.media, 'file_name', None),
                'mime_type': getattr(message.media, 'mime_type', None)
            }
        except Exception as e:
            parsed_message['media_details_error'] = str(e)

    return parsed_message

async def save_message_to_json(message):
    """
    Сохраняет сообщение в JSON-файл
    """
    parsed_msg = parse_message(message)
    filename = os.path.join(OUTPUT_FOLDER, f"message_{parsed_msg['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(parsed_msg, f, ensure_ascii=False, indent=4)
        print(f"Сообщение сохранено: {filename}")
    except Exception as e:
        print(f"Ошибка сохранения сообщения: {e}")

async def main():
    # Создаем клиент Telegram
    client = TelegramClient('session', API_ID, API_HASH)
    
    # Обработчик новых сообщений
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def forward_and_save_messages(event):
        try:
            # Пересылаем сообщение в целевой чат
            await client.send_message(TARGET_CHAT_ID, event.message)
            print(f"Сообщение переслано: {event.message.id}")
            
            # Сохраняем сообщение в JSON
            await save_message_to_json(event.message)
            
        except Exception as e:
            print(f"Ошибка при обработке сообщения: {e}")

    # Подключаемся к клиенту
    await client.start(phone=PHONE_NUMBER)
    print("Бот запущен и ожидает новые сообщения...")
    
    # Держим скрипт активным
    await client.run_until_disconnected()

# Запускаем основную функцию
if __name__ == '__main__':
    asyncio.run(main())
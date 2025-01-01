from telethon import TelegramClient
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем credentials
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')

# Создаем клиент и сессию
client = TelegramClient('session/telegram_session', API_ID, API_HASH)

async def main():
    await client.start(phone=PHONE_NUMBER)
    print("Сессия успешно создана!")
    
# Запускаем
import asyncio
asyncio.run(main())




# from telethon import TelegramClient
# import os
# from dotenv import load_dotenv
# import sys

# # Добавим вывод текущей директории
# print(f"Current directory: {os.getcwd()}")

# # Загружаем .env файл
# env_path = os.path.join(os.path.dirname(__file__), '.env')
# print(f"Looking for .env file at: {env_path}")
# load_dotenv(env_path)

# # Выводим значения (замаскированные)
# api_id = os.getenv('API_ID')
# api_hash = os.getenv('API_HASH')
# phone = os.getenv('PHONE_NUMBER')

# print(f"API_ID loaded: {'Yes' if api_id else 'No'}")
# print(f"API_HASH loaded: {'Yes' if api_hash else 'No'}")
# print(f"PHONE_NUMBER loaded: {'Yes' if phone else 'No'}")

# if not all([api_id, api_hash, phone]):
#     print("Error: Some required environment variables are missing!")
#     sys.exit(1)

# # Используем относительный путь
# session_file = os.path.join('session', 'telegram_session')
# print(f"Session file path: {os.path.abspath(session_file)}")

# client = TelegramClient(session_file, api_id, api_hash)

# async def main():
#     print("Attempting to start client...")
#     await client.start(phone=phone)
#     print("Сессия успешно создана!")
#     await client.disconnect()

# import asyncio
# asyncio.run(main())

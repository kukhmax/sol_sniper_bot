import os
import asyncio
import json
import logging
import requests
from datetime import datetime
from termcolor import colored, cprint
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
PHONE_NUMBER = "+48884098177"

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

    # print(parsed_message['text'])

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

async def rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
        if r.status_code == 200:                
            data = r.json()
            pair_address  = data["markets"][0]["pubkey"]
            symbol = data["tokenMeta"]["symbol"]
            score = data['score']
            risk_descriptions = []
            is_no_danger = True

            if data["risks"]:
                for risk in data["risks"]:
                    risk_descriptions.append(f"{risk['description']} ({risk['level']})")
                    if risk["level"] == "danger":
                        logger.warning(colored(f"Risk is high because {risk['description']}"))
                        is_no_danger = False
                        break
            return pair_address, symbol, score, risk_descriptions, is_no_danger
        logger.warning(colored(f"Status code: {r.status_code} - {r.reason}", "magenta", attrs=["bold"]))
        return None
    except Exception as e:
        logger.error(colored(f"Error rugchecking: {str(e)}"))
        return None

async def main():
    # Создаем клиент Telegram
    client = TelegramClient('session', API_ID, API_HASH)
    
    # Обработчик новых сообщений
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def forward_and_save_messages(event):
        print(f"Сообщение: {event.message.id}")
        try:
            if "New" in event.message.text:
                mint = event.message.text.split("New")[0].split('**](https://t.me/soul_sniper_bot?start=15_')[1].replace(')**', '').strip()
                # print(mint)

                token_name = event.message.text.split("New")[0].split('**](https://t.me/soul_sniper_bot?start=15_')[0].replace('🔥 [**', '').strip()
                print(token_name, '    ', mint)

                print(f"GMGN URL: https://gmgn.ai/sol/token/{mint}")
                print(f"RugCheck: https://api.rugcheck.xyz/v1/tokens/{mint}/report")


                # extract data from rugcheck.xyz
                rug_check = await rugcheck(mint)
                if rug_check:
                    pair_address, symbol, score, risk_descriptions, is_no_danger = rug_check
                    if  is_no_danger:

                        message  = f"""
🔥  **{symbol}**    [{token_name}](https://t.me/solearlytrending/{event.message.id})

📊  __Score__:   [{score}]({f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"})
⚖️  __Risks__:   {'\n        '.join(risk_descriptions)}

📈  **DexScreener**    [link](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)
📈  **GMGN**              [link](https://gmgn.ai/sol/token/{mint})
                        """
                        # Пересылаем сообщение в целевой чат
                        await client.send_message(TARGET_CHAT_ID, message)
                        print(f"Сообщение переслано: {event.message.id}")
                        
                        

            # Сохраняем сообщение в JSON
            # await save_message_to_json(event.message)
            
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



#  # You can, of course, use markdown in your messages:
#     message = await client.send_message(
#         'me',
#         'This message has **bold**, `code`, __italics__ and '
#         'a [nice website](https://example.com)!',
#         link_preview=False
#     )
"""https://docs.telethon.dev/en/stable/basic/quick-start.html"""

import os
import asyncio
import traceback
import logging
import requests
from datetime import datetime
from termcolor import colored, cprint
from telethon import TelegramClient, events
from app.utils import get_token_price, fetch_pool_keys
from solana.exceptions import SolanaRpcException

from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Безопасное получение credentials из переменных окружения
API_ID = os.getenv('API_ID')  # Получите на https://my.telegram.org/apps
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')
PHONE_NUMBER = os.getenv('PHONE_NUMBER')


# ID чатов
SOURCE_CHAT_ID = int(os.getenv('SOURCE_CHAT_ID', '-1002093384030'))
TARGET_CHAT_ID = int(os.getenv('TARGET_CHAT_ID', '7475229862'))


def rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
        print(f"RugCheck API request - status code: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            pair_address = data["markets"][0]["pubkey"]
            symbol = data["tokenMeta"]["symbol"]
            score = data['score']
            risk_descriptions = []
            is_no_danger = True

            if data["risks"]:
                for risk in data["risks"]:
                    risk_descriptions.append(f"{risk['description']} ({risk['level']})")
                    if risk["level"] == "danger":
                        print(colored(f"Risk is high because {risk['description']}", "red"))
                        is_no_danger = False
                        break
            return pair_address, symbol, score, risk_descriptions, is_no_danger
        cprint(f"Status code: {r.status_code} - {r.reason}", "red")
        logging.error(f"RugCheck API error - status code: {r.status_code}, reason: {r.reason}")
        return None
    except Exception as e:
        logging.error(f"Error rugchecking: {str(e)}")
        return None
    
async def track_price(
        pool_keys, symbol, token_name, pair_address,
        start_price, client
):
    last_pnl = 0
    pnl_message = None
    max_pnl = 0

    STOP_LOSS = -10
    TARGET = 50

    while True:
        try:
            current_price, _ = get_token_price(pool_keys)                            
            pnl = ((current_price - start_price) / start_price) * 100

            max_pnl = max(max_pnl, pnl)

            if pnl >= TARGET:
                STOP_LOSS = TARGET - 40
                TARGET += 50

            color_pnl = "🟢🟢🟢" if pnl > 0 else "🔴🔴🔴"

            if pnl > last_pnl + 25:
                cprint(f"{token_name}       Price changed by {pnl - last_pnl:.2f}%!!!", "green", attrs=["bold", "reverse"])
                print(f"Current price  {token_name}: {current_price:.10f}")
                pnl_message = f"""
✔️        **{symbol}** 💹  [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc) 
🟢  Price changed by {pnl - last_pnl:.2f}%!!! 🟢
**[Buy price]**           {start_price:.10f}
**[Current price]**       {current_price:.10f}
**Stop  loss:** {STOP_LOSS}%  ®️  **Max PnL:** {max_pnl:.2f}%
{color_pnl}  Current PnL: {pnl:.2f}  {color_pnl}
                                """
                last_pnl = pnl

            if pnl < last_pnl - 25:
                cprint(f"{token_name}       Price changed by {pnl - last_pnl:.2f}%!!!", "red", attrs=["bold", "reverse"])
                print(f"Current price  {token_name}: {current_price:.10f}")
                pnl_message = f"""
✔️        **{symbol}** 🆘  [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc) 
🔴  Price changed by {pnl - last_pnl:.2f}%!!!  🔴
**[Buy price]**           {start_price:.10f} 
**[Current price]**       {current_price:.10f}
**Stop  loss:**  {STOP_LOSS}%  ®️  **Max PnL:** {max_pnl:.2f}%
{color_pnl}  Current PnL: {pnl:.2f}  {color_pnl}
                                """
                last_pnl = pnl

            if pnl <= STOP_LOSS:
                print(f"Current pnl {token_name}: {pnl:.2f}")
                pnl_side = "❇️🟩❇️" if pnl > 0 else "❌⭕️❌"

                                
                await client.send_message(TARGET_CHAT_ID, f"""
🎯      **{symbol}**   🌐   [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc) 
**[Buy price]**           {start_price:.10f} 
**[Current price]**       {current_price:.10f}
**Max pnl:**     {max_pnl:.2f}%
{pnl_side}  Stop Loss Hit  -  **{STOP_LOSS}%**  {pnl_side}
{color_pnl}  Real PnL:   **{pnl:.2f}%**   {color_pnl}""",
                                          parse_mode="Markdown",
                                          link_preview=False)
                return

            if pnl_message:
                await client.send_message(TARGET_CHAT_ID, 
                                          pnl_message, 
                                          parse_mode="Markdown",
                                          link_preview=False)
                pnl_message = None
            await asyncio.sleep(9)

        except SolanaRpcException:
            cprint("Solana RPC error. Retrying...", "red", attrs=["bold", "reverse"])
            await asyncio.sleep(2.5)
            continue

        except Exception as e:
            cprint(f"Error tracking pnl: {str(e)}", "red", attrs=["bold", "reverse"])
            print(traceback.format_exc())
            continue

async def main():
    # Создаем клиент Telegram
    client = TelegramClient('session', API_ID, API_HASH)

    # Обработчик новых сообщений
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def forward_and_save_messages(event):
        print(f"New message received - ID: {event.message.id}")

        try:

            if "New" in event.message.text:
                mint = event.message.text.split("New")[0].split(
                    '**](https://t.me/soul_sniper_bot?start=15_'
                )[1].replace(')**', '').strip()
                token_name = event.message.text.split("New")[0].split(
                    '**](https://t.me/soul_sniper_bot?start=15_'
                )[0].replace('🔥 [**', '').strip()
                cprint(f"Extracted token data - Name: {token_name}, Mint: {mint}", "black", "on_white")
                age = event.message.text.split("Age**: ")[1][:3].strip()
                cprint(f"Extracted age: {age}", "yellow")

                cprint(f"GMGN URL: https://gmgn.ai/sol/token/{mint}", "light_magenta", "on_blue")
                cprint(f"RugCheck URL: https://api.rugcheck.xyz/v1/tokens/{mint}/report", "light_red")

                # extract data from rugcheck.xyz
                rug_check = rugcheck(mint)
                
                if rug_check:
                    pair_address, symbol, score, risk_descriptions, is_no_danger = rug_check
                    if is_no_danger:

                        message = f"""
🔠🔠🔠  **{symbol}**     |    [{token_name}](https://t.me/solearlytrending/{event.message.id})
⏰  __Time__:  __{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}__
📅  __Age__:   **{age}** 
        ⚖️  **Risks**  ⚖️       🔸[{score}]({f"https://rugcheck.xyz/tokens/{mint}"})🔸
 __{'\\n        '.join(risk_descriptions)}__
    [DexScreener](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)  📈  [GMGN](https://gmgn.ai/sol/token/{mint})
                        """
                        # Пересылаем сообщение в целевой чат
                        await client.send_message(TARGET_CHAT_ID, message, parse_mode="Markdown",
                                                link_preview=False)
                        print(f"Message forwarded to target chat: {event.message.id}")
                        
                        pool_keys = fetch_pool_keys(pair_address)

                        if pool_keys:

                            start_price, _ = get_token_price(pool_keys)
                            cprint(f"Start price  {token_name}: {start_price:.10f}", "light_cyan")

                            await track_price(
                                pool_keys, symbol, token_name,
                                pair_address, start_price, client
                            )

        except Exception as e:
            print(f"Error processing message: {str(e)}")
            print(traceback.format_exc())


    # Подключаемся к клиенту
    try:
        await client.start(phone=PHONE_NUMBER)
        print("Bot started and waiting for new messages...")

        if not client.is_connected():
            raise ConnectionError("Client is not connected.")
        # Держим скрипт активным
        await client.run_until_disconnected()
    except Exception as e:
        logging.error(f"Error during bot startup or connection: {e}")
    finally:
        await client.disconnect()

# Запускаем основную функцию
if __name__ == '__main__':
    asyncio.run(main())
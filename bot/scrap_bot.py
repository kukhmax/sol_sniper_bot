"""https://docs.telethon.dev/en/stable/basic/quick-start.html"""

import os
import asyncio
import traceback
# import logging
import requests
from datetime import datetime
from termcolor import colored, cprint
from telethon import TelegramClient, events
from solana.exceptions import SolanaRpcException
from dotenv import load_dotenv


from app.utils import get_token_price, fetch_pool_keys
from app.track_pnl import RaydiumPnLTracker
from app.raydium import sell, buy
from app.config import RPC, setup_logging, payer_pubkey, client as solana_client

import logging.handlers


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

# В функции main() добавить:
logger = setup_logging()

def rugcheck(mint):
    try:
        r = requests.get(f"https://api.rugcheck.xyz/v1/tokens/{mint}/report")
        logging.debug(colored(f"RugCheck API request - status code: {r.status_code}", "light_yellow"))
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
                        logging.warning(colored(f"Risk is high because {risk['description']}", "red"))
                        is_no_danger = False
                        break
            return pair_address, symbol, score, risk_descriptions, is_no_danger

        logging.error(f"RugCheck API error - status code: {r.status_code}, reason: {r.reason}")
        return None
    except Exception as e:
        logging.error(f"Error rugchecking: {str(e)}")
        return None

def get_balance(client, payer_pubkey):
    try:
        account_info = client.get_account_info(payer_pubkey )

        # Check if account exists
        if account_info.value is None:

            print(f"Account {payer_pubkey} does not exist.")
            return 0.0

        # Get balance in lamports (1 SOL = 10^9 lamports)
        balance_lamports = account_info.value.lamports 
        # Convert lamports to SOL
        balance_sol = balance_lamports / 10**9
        return balance_sol
    except Exception as e:
        logging.error(f"Error getting balance: {str(e)}")
        return 0.0

async def track_price(
        pool_keys, symbol, token_name, pair_address,
        start_price, client, event_id
):
    last_pnl = 0
    pnl_message = None
    max_pnl = 0

    stop_loss = -10
    hundreds = 30

    while True:
        try:
            current_price, _ = get_token_price(pool_keys)
            pnl = ((current_price - start_price) / start_price) * 100

            max_pnl = max(max_pnl, pnl)

            last_stop_loss = 10 if max_pnl >= 30 and max_pnl < 50 else (max_pnl - 35 if max_pnl >= 50 else -5)
            if last_stop_loss > stop_loss:
                stop_loss = last_stop_loss
                logging.info(colored(f"Stop loss updated to {stop_loss:.2f}%", "yellow"))

            if max_pnl > hundreds:
                try:
                    conf, _, token_amount = sell(pair_address, 50, token_symbol=symbol)
                    logging.debug(f"{token_name}  sell txn: confirm - {conf} ; ")
                    if conf:
                        hundreds += 200
                        print(f"hundreds is {hundreds}")
                        await send_message_safely(client,
                                                  TARGET_CHAT_ID, f"""
🎯   **{symbol}**  🌐  [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)
**[Buy price]**           {start_price:.10f}
**[Current price]**       {current_price:.10f}
**Current pnl:**     {pnl:.2f}%
🟢🟢  Sold 50%  **{token_amount}** {symbol}  🟢🟢""",
                                              parse_mode="Markdown",
                                              disable_web_page_preview=True)

                        logging.info(f"\n{symbol} - {token_name} sold 50%  successfully!!! Sold amount: {token_amount} {symbol}                 ")
                        continue
                    else:
                        await send_message_safely(client, 
                                                  TARGET_CHAT_ID,
                                                  f"""
    ❌ Failed to sell {symbol} token ❌
    🟢  Max PnL: **{max_pnl:.2f}%** 🟢""",
                                              parse_mode="Markdown")
                except Exception as e:
                    logging.error(colored(f"\nError selling 50% of token {token_name}: {str(e)}", "magenta", attrs=["bold", "reverse"]))


            color_pnl = "🟢" if pnl > 0 else "🔴"

            if pnl > last_pnl + 30:
                cprint(f"\n{token_name}       Price changed by {pnl - last_pnl:.2f}%!!!          ", "green", attrs=["bold", "reverse"])
                logging.info(f"              Current price  {token_name}: {current_price:.10f}                     ")
                pnl_message = f"""
✔️      **{symbol}** 💹  [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc) 
🟢  Price changed by {pnl - last_pnl:.2f}%!!! 🟢
**[Buy price]**           {start_price:.10f}
**[Current price]**       {current_price:.10f}
**Stop  loss:** {stop_loss:.2f}%  ®️  **Max PnL:** {max_pnl:.2f}%
{color_pnl}  Current PnL: **{pnl:.2f}**  {color_pnl}
                                """
                last_pnl = pnl

            if pnl < last_pnl - 30:
                cprint(f"\n{token_name}       Price changed by {pnl - last_pnl:.2f}%!!!           ", "red", attrs=["bold", "reverse"])
                logging.info(f"              Current price  {token_name}: {current_price:.10f}                       ")
                pnl_message = f"""
✔️      **{symbol}** 🆘  [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc) 
🔴  Price changed by {pnl - last_pnl:.2f}%!!!  🔴
**[Buy price]**           {start_price:.10f} 
**[Current price]**       {current_price:.10f}
**Stop  loss:**  {stop_loss:.2f}%  ®️  **Max PnL:** {max_pnl:.2f}%
{color_pnl}  Current PnL: **{pnl:.2f}**  {color_pnl}
                                """
                last_pnl = pnl

            if pnl <= stop_loss:
                logging.info(colored(f"Current pnl {token_name}: {pnl:.2f}", "light_magenta"))
                pnl_side = "❇️🟩❇️" if pnl > 0 else "❌⭕️❌"
                for _ in range(3):

                    confirm, txn, token_amount = sell(pair_address, 100, token_symbol=symbol)
                    if confirm:
                        await asyncio.sleep(5)
                        # cprint(f"Transaction sent - txn: {txn}", "yellow", attrs=["bold"])
                        try:
                            sol_balance = get_balance(solana_client, payer_pubkey)
                            logging.info(colored(f"Current balance: {sol_balance:.2f}", "green"))
                        except Exception as e:
                            logging.error(colored(f"Error getting balance: {str(e)}", "red", attrs=["reverse"]))
                            sol_balance = "unknown"

                        await send_message_safely(client, 
                                                  TARGET_CHAT_ID,
                                                  f"""
🎯   **[{symbol}](https://t.me/solearlytrending/{event_id})**   🌐   [{token_name}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)
💰  Sol balance: **{sol_balance:.5f}**
**[Buy price]**           {start_price:.10f} 
**[Current price]**       {current_price:.10f}
**Max pnl:**     {max_pnl:.2f}%  Stop_loss: {stop_loss:.2f}%
{pnl_side}  Stop Loss Hit:    **{pnl:.2f}%**   {pnl_side}
      Sold **{token_amount:.2f}** {symbol}""",
                                                parse_mode="Markdown",
                                                link_preview=False)
                        logging.info(colored(f"\n {symbol} - {token_name} sold successfully!!! Sold amount: {token_amount} {symbol}\n", "yellow"))
                        return
                    else:
                        logging.error(colored("Error sending transaction", "red", attrs=["reverse"]))
                        continue
                logging.error(colored(f"Sell {token_name} transaction failed 3 times. Trying later...", "red", attrs=["bold", "reverse"]))
                await send_message_safely(client, 
                                          TARGET_CHAT_ID,
                                          f"""
🎯   **[{symbol}](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)**
🔴🔴  Sell transaction **{token_name}** 🔴🔴
      🔴🔴  __failed 3 times.__  🔴🔴
       🔴🔴  **Try manualy...** 🔴🔴
              Pnl: **{pnl:.2f}%**""",
                                    parse_mode="Markdown",
                                    link_preview=False)
                return

            if pnl_message:
                await send_message_safely(client, 
                                          TARGET_CHAT_ID, 
                                          pnl_message, 
                                          parse_mode="Markdown",
                                          link_preview=False)
                pnl_message = None
            await asyncio.sleep(5)

        except SolanaRpcException:
            logging.critical(colored("Solana RPC error. Retrying...", "red", attrs=["bold", "reverse"]))
            await asyncio.sleep(2.5)
            continue

        except Exception as e:
            logging.error(colored(f"Error tracking pnl: {str(e)}", "red", attrs=["bold", "reverse"]))
            print(traceback.format_exc())
            continue

async def send_message_safely(client, target_id, message, **kwargs):
    try:
        # Пробуем отправить напрямую
        return await client.send_message(target_id, message, **kwargs)
    except ValueError:
        try:
            # Пробуем получить entity другим способом
            entity = await client.get_entity('t.me/sniper_raydium_bot')
            return await client.send_message(entity, message, **kwargs)
        except Exception as e:
            logging.error(f"Failed to send message: {e}")
            return None

async def main():
    # Создаем клиент Telegram
    client = TelegramClient('session/telegram_session', API_ID, API_HASH)

    # Обработчик новых сообщений
    @client.on(events.NewMessage(chats=SOURCE_CHAT_ID))
    async def forward_and_save_messages(event):
        id = event.message.id
        logging.info(colored(f"New message received - ID: {event.message.id}", "light_blue"))

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
                cprint(f"\nGMGN URL: https://gmgn.ai/sol/token/{mint}", "light_magenta")
                cprint(f"DexScreener URL: https://dexscreener.com/solana/{mint}\n", "magenta")

                rug_check = rugcheck(mint)

                if rug_check:
                    pair_address, symbol, score, risk_descriptions, is_no_danger = rug_check
                    if is_no_danger:

                        pool_keys = fetch_pool_keys(pair_address)

                        if pool_keys:

                            balance = get_balance(solana_client, payer_pubkey)
                            logging.info(colored(f"Solana balance: {balance}", "light_green", attrs=["bold"]))

                            txn, confirm = buy(pair_address, pool_keys, 0.006, 5, token_symbol=symbol)
                            logging.info(colored(f"Buy transaction: {str(txn)[:5]}...{str(txn)[-5:]}, confirm: {confirm}", "light_green", attrs=["bold"]))
                            wsol = "So11111111111111111111111111111111111111112"
                            if confirm:
                                while True:
                                    tracker = RaydiumPnLTracker(pair_address, mint, wsol, 0.001, RPC)
                                    try:
                                        start_price, token_amount, _ = tracker.get_current_price(txn)

                                        logging.info(colored(f"\n    Buy price: {start_price:.10f}", "light_green", attrs=["bold"]))
                                        break
                                    except Exception as e:
                                        logging.error(f"Error getting current price: {e}")
                                        await asyncio.sleep(3)

                                message = f"""
🔠  **{symbol}**     |    [{token_name}](https://t.me/solearlytrending/{event.message.id})
⏰  __Time__:  __{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}__
📅  __Age__:   **{age}**
    **Price**: {start_price:.10f} SOL. 
💰  **Amount:** {token_amount:.2f} {symbol}
💰  Sol balance: **{balance:.5f}**
   ⚖️  **Risks**  ⚖️       🔸[{score}]({f"https://rugcheck.xyz/tokens/{mint}"})🔸
 __{'\n '.join(risk_descriptions)}__
    [DexScreener](https://dexscreener.com/solana/{pair_address}?maker=4NZNfmNPfejj2YvAqSzbKTukDbz5FTiwBAdifAAGVrMc)  📈  [GMGN](https://gmgn.ai/sol/token/{mint})
                        """

                                await send_message_safely(client, 
                                                          TARGET_CHAT_ID,
                                                          message,
                                                          parse_mode="Markdown",
                                                          link_preview=False)
                                logging.info(colored(f" Message forwarded to target chat: {event.message.id}", "dark_grey", "on_cyan"))

                                await track_price(
                                    pool_keys, symbol, token_name,
                                    pair_address, start_price, client, id
                                )

        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")
            print(traceback.format_exc())

    # Подключаемся к клиенту
    try:
        await client.start(phone=PHONE_NUMBER)        
        logging.info(colored("Bot started and waiting for new messages...", "green", "on_white", attrs=["bold"]))

        # Добавляем получение информации о целевом пользователе при старте
        try:
            target_user = await client.get_entity(TARGET_CHAT_ID)
            logging.info(f"                Successfully retrieved target user: {target_user.first_name}")
        except Exception as e:
            logging.error(f"Error getting target user: {e}")
            # Можно попробовать альтернативный способ
            target_user = await client.get_input_entity('t.me/sniper_raydium_bot')

        if not client.is_connected():
            raise ConnectionError("Client is not connected.")
        # Держим скрипт активным
        await client.run_until_disconnected()
    except Exception as e:
        logging.critical(f"Error during bot startup or connection: {str(e)}")
    finally:
        await client.disconnect()

# Запускаем основную функцию
if __name__ == '__main__':
    asyncio.run(main())

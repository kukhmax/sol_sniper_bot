import os
import json
from datetime import datetime
from time import sleep
import logging
import asyncio
from typing import AsyncIterator, Tuple
from asyncstdlib import enumerate
from pip._vendor.typing_extensions import Iterator
from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solana.rpc.websocket_api import connect
from solana.rpc.commitment import Finalized
from solana.rpc.api import Client
from solana.exceptions import SolanaRpcException
from websockets.exceptions import ConnectionClosedError, ProtocolError
from typing import List

# Type hinting imports
from solana.rpc.commitment import Commitment
from solana.rpc.websocket_api import SolanaWsClientProtocol
from solders.rpc.responses import RpcLogsResponse, SubscriptionResult, LogsNotification, GetTransactionResp
from solders.signature import Signature
from solders.transaction_status import UiPartiallyDecodedInstruction, ParsedInstruction
import requests
import math

from termcolor import colored, cprint


# Raydium Liquidity Pool V4
RaydiumLPV4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
URI = "https://api.mainnet-beta.solana.com"  # "https://api.devnet.solana.com" | "https://api.mainnet-beta.solana.com"
WSS = "wss://api.mainnet-beta.solana.com"  # "wss://api.devnet.solana.com" | "wss://api.mainnet-beta.solana.com"
solana_client = Client(URI)
METADATA_PROGRAM_ID = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
LAMPORTS_PER_SOL = 1000000000

log_instruction = "init_pc_amount"
# log_instruction = "initialize2"

# Init logging
logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.DEBUG, 
    format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",  # Формат логов с именем функции и номером строки
    datefmt="%Y-%m-%d %H:%M:%S"
    )

async def subscribe_to_logs(
        websocket: SolanaWsClientProtocol,
        mentions: RpcTransactionLogsFilterMentions,
        commitment: Commitment
) -> int:
    await websocket.logs_subscribe(filter_=mentions,commitment=commitment)
    first_resp = await websocket.recv()
    return first_resp[0].result

async def process_messages(
        websocket: SolanaWsClientProtocol,
        instruction: str
) -> AsyncIterator[Signature]:
    """Асинхронный генератор, основной цикл websocket-соединения"""
    async for idx, msg in enumerate(websocket):
        value = msg[0].result.value

        if not idx % 10000:
            cprint(f"Received {idx} messages", "yellow", "on_grey")

        for log in value.logs:
            if instruction not in log:
                continue

            logging.info(value.signature)
            logging.info(log)

            # Logging to messages.json
            with open("messages.json", 'a', encoding='utf-8') as raw_messages:
                raw_messages.write(f"'signature': {value.signature} \n")
                raw_messages.write(msg[0].to_json())
                raw_messages.write("\n ########## \n")
            yield value.signature

def get_tokens_info(
        instruction: UiPartiallyDecodedInstruction | ParsedInstruction
) -> Tuple[Pubkey, Pubkey, Pubkey]:
    accounts = instruction.accounts
    
    Pair = accounts[4]
    Token0 = accounts[8]
    Token1 = accounts[9]
    # Start logging
    logging.info("find LP !!!")
    logging.info(f"\n Token0: {Token0}, \n Token1: {Token1}, \n Pair: {Pair}")
    # cprint(f"Token0: {Token0}, \n Token1: {Token1}, \n Pair: {Pair}", "green", "on_white")

    return Token0, Token1, Pair

def get_basemint(instruction: UiPartiallyDecodedInstruction):
    accounts = instruction.accounts

    if accounts[8] != "So11111111111111111111111111111111111111112":
        base_mint = accounts[8]
        quote_mint = accounts[9]
    else:
        quote_mint = accounts[8]     
        base_mint = accounts[9]
    
    if base_mint == "So11111111111111111111111111111111111111112":
        base_mint = quote_mint
    
    return base_mint

async def calc_LP_locked_pct(
    transaction: GetTransactionResp,
    instruction: UiPartiallyDecodedInstruction,
    signature: Signature):
    """Извлекает LPRESERVE и рассчитать процент сжигания LP из заданной instruction и signature."""
    
    accounts = instruction.accounts
    lpReserve = -69
    meta_data = transaction.value.transaction.meta
    inner_instructions = meta_data.inner_instructions  # initializeMint

    for inner_instruction in inner_instructions:
        # print(inner_instruction)
        for data in inner_instruction.instructions:
            # получаем данные инструкции
            # print(data)
            try:
                #  accounts[7]  === адрес LP токена
                if Pubkey.from_string(data.parsed['info']['mint']) == accounts[7] and data.parsed['type'] == 'mintTo':
                    lp_reserve = data.parsed['info']['amount']
                    lp_reserve_ = data.parsed['info']['amount']
                    cprint(f"LP Reserve: {lp_reserve}", "green")
                    continue
                if Pubkey.from_string(y.parsed['info']['mint']) == accounts[7] and y.parsed['type'] == 'initializeMint':
                    lp_decimals = y.parsed['info']['decimals']
                    cprint(f"lpDecimals: {lp_decimals}", "green")
                    continue
                if Pubkey.from_string(y.parsed['type']) == accounts[7] and y.parsed['type'] == 'initializeMint':
                    lp_decimals = y.parsed['info']['decimals']
                    cprint(f"lpDecimals: {lp_decimals}", "green")
                    continue

            except Exception as e:
                # cprint(str(e), "red", attrs=["reverse", "blink"])
                continue
    
        # ================= ВЫЧИСЛЯЕМ СОЖЖЕНЫ ЛИ LP ТОКЕНЫ ================

    # получаем информацию о LP токене  в  формате json           
    account_info = solana_client.get_account_info_json_parsed(accounts[7])
    # account_info_json = json.loads(account_info.to_json())
    # cprint(f"account_info_json: {account_info_json}", "yellow")
    try:
        ...
    except Exception as e:
        cprint(f"Ошибка при проверски BURN TOKENS: {str(e)}", "red", attrs=["reverse", "blink"])

    

async def get_tokens(signature: Signature, RaydiumLPV4: Pubkey) -> None:
    transaction = solana_client.get_transaction(
        signature,
        encoding="jsonParsed",
        max_supported_transaction_version=0
    )
    # cprint(f"Print transaction RAW:\n{transaction}", "green", "on_white")
    # cprint(f"Print signature RAW:\n{signature}", "black", "on_yellow")
    # cprint(f"Print transaction.to_json():\n{transaction.to_json()}", "green", "on_white")

    with open("transactions.json", 'a', encoding='utf-8') as raw_transactions:
        raw_transactions.write(f"'signature': {signature}\n")
        raw_transactions.write(transaction.to_json())
        raw_transactions.write("\n ########## \n")
    
    instructions = transaction.value.transaction.transaction.message.instructions
    # cprint(f"Print instructions RAW:\n{instructions}", "grey")

    # фильтруем по program_id (в данном случае - RaydiumLPV4)
    filtered_instructions = (
        instruction for instruction in instructions if instruction.program_id == RaydiumLPV4
    )
    logging.info(f"Print filtered instructions RAW:\n{filtered_instructions}")

    for instruction in filtered_instructions:
        tokens = get_tokens_info(instruction)

        # выводим в консоль данные токенов
        data = [
            {'Token_Index': 'Token0', 'Account Public Key': tokens[0]},  # Token0
            {'Token_Index': 'Token1', 'Account Public Key': tokens[1]},  # Token1
            {'Token_Index': 'LP Pair', 'Account Public Key': tokens[2]}  # LP Pair
        ]
        print()
        cprint("=========================================", "magenta", "on_white", attrs=['bold'])
        cprint("=========== NEW POOL DETECTED ===========", "magenta", "on_white", attrs=['bold'])
        cprint("=========================================", "magenta", "on_white", attrs=['bold'])
        header = ["Token_Index", "Account Public Key"]
        print()
        cprint("│".join(f" {col.ljust(15)} " for col in header), "white", "on_blue")
        print()
        for row in data:
            cprint("│".join(f" {str(row[col]).ljust(15)} " for col in header), "white", "on_blue")
        print()
        cprint(f"Link to DEXScreener: https://dexscreener.com/solana/{tokens[2]}", "red", "on_yellow")
        cprint(f"Link to Solscan: https://solscan.io/tx/{signature}", "red", "on_white", attrs=['bold'])

        # =================================
        # HERE HERE HERE HERE HERE HERE HERE
        # THIS IS WHERE WE CALL FUNCTION TO
        # GATHER POOL KEY DATA
        # =================================

        mint = tokens[0] if "111111111111111111111111111111111111" in str(tokens[1]) else tokens[1]
        cprint(f"Token minted is: {mint}", "black", "on_light_yellow")

        myCalc_lpLockedPct = await calc_LP_locked_pct(transaction, instruction, signature)



async def main():
    """Бесконечный асинхронный цикл"""
    async for websocket in connect(WSS):
        try:
            subscription_id = await subscribe_to_logs(
                websocket,
                RpcTransactionLogsFilterMentions(RaydiumLPV4),
                Finalized # Узел запросит самый последний блок, подтвержденный большинством кластера как достигший максимальной блокировки, что означает, что кластер распознал этот блок как завершенный.
            )

            # меняем уровень логирования
            logging.getLogger().setLevel(logging.INFO) 
            
            async for i, signature in enumerate(process_messages(websocket, log_instruction)):
                logging.info(f"{i=}")

                try:
                    await get_tokens(signature, RaydiumLPV4) 
                except (AttributeError, SolanaRpcException) as err:
                     # Omitting httpx.HTTPStatusError: Client error '429 Too Many Requests'
                    logging.exception(err)
                    logging.info("sleep for 5 seconds and try again")
                    cprint(f"Danger! Danger!\n{err}\nSleep for 5 seconds and try again", "red", attrs=["reverse", "blink"])
                    sleep(5)
                    continue

        except (ProtocolError, ConnectionClosedError) as err:
            # Restart socket connection if ProtocolError: invalid status code
            logging.exception(err)  # Logging
            cprint(f"Danger! Danger!\n{err}", "red", attrs=["reverse", "blink"])
            continue
        except KeyboardInterrupt:
            if websocket:
                await websocket.logs_unsubscribe(subscription_id)

# Поиск новых пар добавленных в пул
if __name__ == "__main__":
    RaydiumLPV4 = Pubkey.from_string(RaydiumLPV4)
    asyncio.run(main())
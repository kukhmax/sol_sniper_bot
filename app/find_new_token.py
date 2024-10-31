import os
import json
import pandas as pd
from datetime import datetime
from time import sleep
import logging
import asyncio
from typing import AsyncIterator, Tuple
from asyncstdlib import enumerate
from pip._vendor.typing_extensions import Iterator

from solana.rpc.websocket_api import connect
from solana.rpc.commitment import Finalized, Commitment
from solana.rpc.api import Client
from solana.exceptions import SolanaRpcException
from solana.rpc.websocket_api import SolanaWsClientProtocol
from websockets.exceptions import ConnectionClosedError, ProtocolError

from solders.pubkey import Pubkey
from solders.rpc.config import RpcTransactionLogsFilterMentions
from solders.signature import Signature
from solders.transaction_status import UiPartiallyDecodedInstruction, ParsedInstruction

from termcolor import colored, cprint


# Raydium Liquidity Pool V4
RaydiumLPV4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
URI = "https://api.mainnet-beta.solana.com"  #"https://api.devnet.solana.com" # | "https://api.mainnet-beta.solana.com"
WSS = "wss://api.mainnet-beta.solana.com"  #"wss://api.devnet.solana.com"  # | "wss://api.mainnet-beta.solana.com"
solana_client = Client(URI)
log_instruction = "init_pc_amount"
# log_instruction = "initialize2"

logging.basicConfig(
    filename='app.log',
    filemode='a',
    level=logging.DEBUG, 
    format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
    )

async def subscribe_to_logs(
        websocket: SolanaWsClientProtocol,
        mentions: RpcTransactionLogsFilterMentions,
        commitment: Commitment
) -> int:
    """
    Subscribes to Solana transaction logs using a websocket connection.

    Args:
        websocket: An instance of SolanaWsClientProtocol to interact with websocket.
        mentions: A filter object specifying transaction logs to subscribe to.
        commitment: The level of commitment desired for the subscription.

    Returns:
        An integer representing the subscription ID for the logs subscription.
    """
    await websocket.logs_subscribe(filter_=mentions,commitment=commitment)
    first_resp = await websocket.recv()
    return first_resp[0].result

async def process_messages(
        websocket: SolanaWsClientProtocol,
        instruction: str
) -> AsyncIterator[Signature]:
    """
    Processes incoming transaction logs from a websocket connection,
    filtering by the given instruction.

    Args:
        websocket: An instance of SolanaWsClientProtocol to interact with websocket.
        instruction: The instruction string to filter logs by.

    Yields:
        Signatures of transaction logs containing the given instruction.
    """
    async for idx, msg in enumerate(websocket):
        value = msg[0].result.value

        if not idx % 10000:
            cprint(f"Received {idx} messages", "yellow", "on_grey")

        for log in value.logs:
            if instruction not in log:
                continue

            logging.info(f"Signature: \n{value.signature}")
            logging.info(f"Log: \n{log}")

            # Logging to messages.json
            with open("messages.json", 'a', encoding='utf-8') as raw_messages:
                raw_messages.write(f"'signature': {value.signature}, \n")
                raw_messages.write(msg[0].to_json())
                raw_messages.write("\n \n")
            yield value.signature

def get_tokens_info(
        instruction: UiPartiallyDecodedInstruction | ParsedInstruction
) -> Tuple[Pubkey, Pubkey, Pubkey]:
    """
    Extracts token0, token1, and pair Pubkey from given instruction

    Args:
        instruction: ParsedInstruction or UiPartiallyDecodedInstruction

    Returns:
        Tuple[Pubkey, Pubkey, Pubkey]: (token0, token1, pair)
    """
    accounts = instruction.accounts
    pair = accounts[4]
    token0 = accounts[8]
    token1 = accounts[9]
    # Start logging
    logging.info("find LP !!!")
    logging.info(f"\n Token0: {token0}, \n Token1: {token1}, \n Pair: {pair}")
    return token0, token1, pair

def save_to_csv(data, filename="pool_data.csv"):
    df = pd.DataFrame(data)
    if not os.path.isfile(filename):
        df.to_csv(filename, index=False)
    else:
        df.to_csv(filename, mode='a', header=False, index=False)

async def get_tokens(signature: Signature, RaydiumLPV4: Pubkey) -> None:
    """
    Get token0, token1, and pair Pubkey from given signature

    Args:
        signature: Signature of the transaction
        RaydiumLPV4: Pubkey of RaydiumLPV4 program

    Returns:
        None
    """
    transaction = solana_client.get_transaction(
        signature,
        encoding="jsonParsed",
        max_supported_transaction_version=0
    )
    with open("transactions.json", 'a', encoding='utf-8') as raw_transactions:
        raw_transactions.write(f"'signature': {signature},\n")
        raw_transactions.write(transaction.to_json())
        raw_transactions.write("\n\n")
    
    instructions = transaction.value.transaction.transaction.message.instructions

    # фильтруем по program_id (в данном случае - RaydiumLPV4)
    filtered_instructions = (
        instruction for instruction in instructions if instruction.program_id == RaydiumLPV4
    )
    logging.info(f"Print filtered instructions RAW:\n{filtered_instructions}")

    pool_data = []
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
        cprint(f"Link to raydium pool: https://api.raydium.io/v2/ammV3/ammPool/{tokens[2]}", "white", "on_blue")
        cprint(f"Link to DEXScreener: https://dexscreener.com/solana/{tokens[2]}", "red", "on_yellow")
        cprint(f"Link to Solscan: https://solscan.io/tx/{signature}", "red", "on_white", attrs=['bold'])
        

        mint = tokens[0] if "111111111111111111111111111111111111" in str(tokens[1]) else tokens[1]
        cprint(f"Link to RugCheck: https://api.rugcheck.xyz/v1/tokens/{mint}/report", "green")


        pool_data.append ({
            'Token0': tokens[0],
            'Token1': tokens[1],
            'LP Pair': tokens[2], 
            'Signature': signature,
            'Solscan': f"https://solscan.io/tx/{signature}",
            'DEXScreener': f"https://dexscreener.com/solana/{tokens[2]}",
            'RugCheck': f"https://api.rugcheck.xyz/v1/tokens/{mint}/report"
        })
        # Save data to CSV after each transaction
        save_to_csv(pool_data)

        break

async def find_new_tokens():
    """
    Subscribe to logs of the RaydiumLPV4 program and 
    process every log instruction that mentions the program.

    This function will run indefinitely until it is manually stopped.
    """
    async for websocket in connect(WSS):
        try:
            subscription_id = await subscribe_to_logs(
                websocket,
                RpcTransactionLogsFilterMentions(RaydiumLPV4),
                Finalized # Узел запросит самый последний блок, подтвержденный большинством кластера как достигший максимальной блокировки,
                          # что означает, что кластер распознал этот блок как завершенный.
            )
            # меняем уровень логирования
            logging.getLogger().setLevel(logging.INFO) 
            
            async for i, signature in enumerate(process_messages(websocket, log_instruction)):
                logging.info(f"{i}")

                try:
                    await get_tokens(signature, RaydiumLPV4) 
                except (AttributeError, SolanaRpcException) as err:
                     # Omitting httpx.HTTPStatusError: Client error '429 Too Many Requests'
                    logging.exception(err)
                    logging.info("sleep for 5 seconds and try again")
                    cprint(f"========= Danger! Danger! ==========\n{err}\nSleep for 5 seconds and try again", "red", attrs=["reverse", "blink"])
                    sleep(5)
                    continue

        except (ProtocolError, ConnectionClosedError) as err:
            # Restart socket connection if ProtocolError: invalid status code
            logging.exception(err)
            cprint(f"Danger! Danger!\n{err}", "red", attrs=["reverse", "blink"])
            continue
        except KeyboardInterrupt:
            if websocket:
                await websocket.logs_unsubscribe(subscription_id)

# Поиск новых пар добавленных в пул
if __name__ == "__main__":
    RaydiumLPV4 = Pubkey.from_string(RaydiumLPV4)
    asyncio.run(find_new_tokens())
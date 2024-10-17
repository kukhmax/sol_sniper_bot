import asyncio
import json
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solana.rpc.websocket_api import connect
from solders.instruction import Instruction
from solders.transaction import Transaction
from termcolor import colored, cprint

# Constants
RPC_ENDPOINT = "https://api.mainnet-beta.solana.com"
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")

def is_token_creation(instruction: Instruction) -> bool:
    return instruction.program_id == TOKEN_PROGRAM_ID and instruction.data[0] == 0

def is_liquidity_pool_creation(transaction: Transaction) -> bool:
    # This is a simplified check. You may need to adjust based on specific DEX protocols.
    return any(len(ix.accounts) > 3 for ix in transaction.instructions)


async def monitor_transactions():
        
    async with connect("wss://api.devnet.solana.com") as websocket:
        cprint("Connected to Solana WebSocket", "black", "on_yellow")

        await websocket.logs_subscribe()
        first_resp = await websocket.recv()
        subscription_id = first_resp[0].result
        cprint(f"Subscription ID: {subscription_id}", "cyan", "on_white")
        async for msg in websocket:
           
            logs = msg[0].result.value.logs           
            signature = msg[0].result.value.signature
            
            # Проверяем, если транзакция связана с созданием токенов
            for log in logs:
                if "Pool" in log:
                    # Это событие указывает на создание нового токена
                    cprint(msg, "light_green")
                    # Пытаемся найти mint-адрес токена
                    extract_mint_address(signature)

        # Отменяем подписку
        await websocket.logs_unsubscribe(subscription_id)


def extract_mint_address(signature):

    http_client = Client("https://api.devnet.solana.com")
    try:
        tx = http_client.get_transaction(signature)
        cprint(f"Transaction: {tx}", "green", attrs=["dark"])
        if tx and tx.transaction:
            transaction = tx.transaction.transaction
            
            new_token = any(is_token_creation(ix) for ix in transaction.instructions)
            new_pool = is_liquidity_pool_creation(transaction)
            
            if new_token and new_pool:
                cprint(f"New token and liquidity pool created in transaction: {signature}", "green", "on_light_magenta", attrs=["dark"])
                # You can add more detailed logging or processing here
    except Exception as e:
        cprint(f"Error processing transaction {signature}: {str(e)}", "white", "on_red")


    # return transaction
  



# Запускаем функцию мониторинга
asyncio.run(monitor_transactions())


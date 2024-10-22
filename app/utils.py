import os
import asyncio
import base64

import aiohttp
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair  # type: ignore
from solders.transaction import Transaction  # type: ignore

from termcolor import colored, cprint

async def perform_swap():
    
    async with AsyncClient("https://api.mainnet-beta.solana.com") as client:
        keypair = Keypair.from_base58_string(os.getenv("PRIVATE_KEY"))

        # Получение баланса аккаунта
        balance = await client.get_balance(keypair.pubkey())
        cprint(f"Account balance: {balance.value / 10**9} SOL", "green", "on_light_magenta")

        # Параметры свопа
        params = {
            "from": "6SHQdkjFUiXMbpqBSLUCQ7cVy2xDi4gHFA7MfpCxfReG",
            "to": "So11111111111111111111111111111111111111112",
            
            "amount": 38.60705,
            "payer": str(keypair.pubkey()),
            "slip": 10,  # Slippage
            "fee": 0.00009,  # Priority fee
            "txType": "legacy"  # Change to "v0" for versioned transaciotns
        }

        try:
            async with aiohttp.ClientSession() as session:
                # Получение транзакции свопа
                async with session.get(f"https://swap.solxtence.com/swap", params=params) as response:
                    data = await response.json()
                    # cprint(f"Swap API response: {data}", "white", "on_blue")

                    serialized_tx = base64.b64decode(
                        data["transaction"]["serializedTx"]
                    )
                    # cprint(f"Serialized transaction: {serialized_tx}", "white", "on_blue")
                    tx_type = data["transaction"]["txType"]

            # Получение последнего blockhash
            recent_blockhash = await client.get_latest_blockhash()
            blockhash = recent_blockhash.value.blockhash

            # Deserialize and sign the transaction
            if tx_type == "legacy":
                transaction = Transaction.from_bytes(serialized_tx)
                
                transaction.sign([keypair], blockhash)
                cprint(f"Transaction : {transaction}", "yellow", "on_light_grey")
            else:
                cprint("Unsupported transaction type", "red", attrs=["reverse", "blink"])
                return
            
            signature = await client.send_raw_transaction(bytes(transaction))
            # Send and confirm the transaction
            cprint(f"Transaction sent. Signature: {signature.value}", "magenta", "on_yellow")

            confirmation = await client.confirm_transaction(signature.value)
            cprint(f"Transaction confirmed. Status: {confirmation.value.status}", "green", "on_light_blue")
            if confirmation.value.err:
                cprint(f"Transaction failed: {confirmation.value.err}", "red", attrs=["reverse", "blink"])
            else:
                cprint(f"Swap successful! Transaction signature: {signature.value}", "magenta", "on_yellow")
        except Exception as error:
            cprint(f"Error performing swap: {error}", "red", attrs=["reverse", "blink"])


if __name__ == "__main__":
    asyncio.run(perform_swap())

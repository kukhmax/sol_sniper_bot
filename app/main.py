import os
import base58
from solders.keypair import Keypair  #  type: ignore
from solanatracker import SolanaTracker
from termcolor import colored, cprint
import asyncio
import time

from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

SECRET_KEY = os.getenv("PRIVATE_KEY")

async def swap():
    start_time = time.time()

    keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))  # Replace with your base58 private key
    
    
    solana_tracker = SolanaTracker(keypair, "https://rpc.solanatracker.io/public?advancedTx=true")
    
    swap_response = await solana_tracker.get_swap_instructions(
        "So11111111111111111111111111111111111111112",  # From Token
        "AxpMnAXBsGfwX6LXGn221Q4ZXULUvTmMNfX8SkZGpump",  # To Token
        0.003,  # Amount to swap
        10,  # Slippage
        str(keypair.pubkey()),  # Payer public key
        0.00005,  # Priority fee (Recommended while network is congested)
    )

    
    # Define custom options
    custom_options = {
        "send_options": {"skip_preflight": True, "max_retries": 5},
        "confirmation_retries": 50,
        "confirmation_retry_timeout": 1000,
        "last_valid_block_height_buffer": 200,
        "commitment": "processed",
        "resend_interval": 1500,
        "confirmation_check_interval": 100,
        "skip_confirmation_check": False,
    }
    
    try:
        send_time = time.time()
        txid = await solana_tracker.perform_swap(swap_response, options=custom_options)
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        cprint(f"Transaction ID: {txid}", "green", "on_white")
        cprint("Transaction URL:", f"https://solscan.io/tx/{txid}", "red", "on_yellow")
        cprint(f"Swap completed in {elapsed_time:.2f} seconds", "white", "on_blue")
        cprint(f"Transaction finished in {end_time - send_time:.2f} seconds", "white", "on_green")
    except Exception as e:
        end_time = time.time()
        elapsed_time = end_time - start_time
        cprint(f"Swap failed:  {str(e)}", "red", attrs=["bold", "reverse"])
        cprint(f"Time elapsed before failure: {elapsed_time:.2f} seconds", "white", "on_red")
        # Add retries or additional error handling as needed

if __name__ == "__main__":
    asyncio.run(swap())
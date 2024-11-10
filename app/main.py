import os
import base58
import requests
from solders.keypair import Keypair  #  type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solanatracker import SolanaTracker
from termcolor import colored, cprint
import asyncio
import time
import json
from datetime import datetime

from find_new_token import find_new_tokens
from track_pnl import RaydiumPnLTracker

from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

RaydiumLPV4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
SECRET_KEY = os.getenv("PRIVATE_KEY")
AMOUNT = 0.1
SLIPPAGE = 10
PRIORITY_FEE = 0.00005

async def swap(pool_id, from_token, to_token, amount, slippage, priority_fee):

    """
    Perform a swap using the solana-tracker API.

    Parameters:
    pool_id (str): The ID of the Raydium pool to swap in.
    from_token (str): The token to sell in the swap.
    to_token (str): The token to buy in the swap.
    amount (float): The amount of from_token to sell (in Lamports).
    slippage (float): The maximum allowed slippage in percent.
    priority_fee (float): The priority fee in SOL to pay for the transaction.

    Returns:
    str: The transaction ID of the swap.
    """
    start_time = time.time()

    keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))  # Replace with your base58 private key
    payer = str(keypair.pubkey())
    
    solana_tracker = SolanaTracker(keypair, "https://rpc.solanatracker.io/public?advancedTx=true")
    
    swap_response = await solana_tracker.get_swap_instructions(
        from_token,
        to_token,
        amount,
        slippage,
        payer,
        priority_fee,  # Recommended while network is congested
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

        cprint(f"Transaction URL: https://dexscreener.com/solana/{pool_id}?maker={payer}", "yellow", "on_blue")
        
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

async def main():
    RaydiumLPV4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
    max_retries = 5
    retry_delay = 2

        
    for attempt in range(max_retries):
        try:        
            data = await find_new_tokens(RaydiumLPV4)
            if data:
                break
        except Exception as e:
            cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
            await asyncio.sleep(10)
        
    tracker = RaydiumPnLTracker(data[2], data[0], data[1], 0.1)
    while True:
        try:
            cprint("finding current price...", "yellow")
            await asyncio.sleep(5)
            start_price, cost_with_fee = tracker.get_price_for_current_transaction()
            cprint("tracking PnL...", "green", attrs=["bold"])
            
            if start_price:
                await asyncio.sleep(20)
                _, _, pnl_percentage = tracker.track_pnl(start_price, cost_with_fee)
                with open("pnl.txt", "a") as f:
                    f.write(f"{datetime.now().strftime('%d-%m %H:%M:%S')} - {pnl_percentage:.2f}%\n")
                break
        except Exception as e:
            cprint(f"Error while tracking PnL: {str(e)}", "red", attrs=["bold", "reverse"])


                    # if data:
                    #     pool_id = data[2]
                    #     from_token = data[0]
                    #     to_token = data[1]
                    #     rug_check = f"https://api.rugcheck.xyz/v1/tokens/{to_token}/report"

                        
                        
                        
                        # try:
                        #     # get_current_transaction(pool_id, from_token, to_token)
                            
                        #     # await swap(pool_id, from_token, to_token, AMOUNT, SLIPPAGE, PRIORITY_FEE)
                        #     pass
                        # except Exception as e:
                        #     cprint(f"Swap failed (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
                        #     if attempt < max_retries - 1:
                        #         await asyncio.sleep(retry_delay * (attempt + 1))
                        #     else:
                        #         raise Exception(f"Failed to complete swap after {max_retries} attempts")
                
        except Exception as e:
            cprint(f"Error in main loop (attempt {attempt + 1}/{max_retries}): {str(e)}", "red", attrs=["bold"])
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())







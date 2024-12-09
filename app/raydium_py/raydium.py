import base64
import os

from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts, TxOpts

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price  # type: ignore
from solders.message import MessageV0  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solders.system_program import (
    CreateAccountWithSeedParams,
    TransferParams,
    create_account_with_seed,
    transfer
)
from solders.transaction import VersionedTransaction  # type: ignore

from spl.token.client import Token
from spl.token.instructions import (
    CloseAccountParams,
    InitializeAccountParams,
    close_account,
    create_associated_token_account,
    get_associated_token_address,
    initialize_account
)
from termcolor import colored, cprint
import logging

from config import client, payer_keypair, UNIT_BUDGET, UNIT_PRICE
from constants import SOL_DECIMAL, SOL, TOKEN_PROGRAM_ID, WSOL
from layouts import ACCOUNT_LAYOUT
from utils import confirm_txn, fetch_pool_keys, get_token_price, make_swap_instruction, get_token_balance

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
    handlers=[
        logging.FileHandler('raydium.log'),
        logging.StreamHandler()
    ]
)


def buy(pair_address: str, sol_in: float = .01, slippage: int = 5) -> bool:
    try:
        cprint(f"Starting buy transaction for pair address: {pair_address}", "yellow", "on_blue", attrs=["bold"])
        
        cprint("Fetching pool keys...", "green", attrs=["bold"])
        pool_keys = fetch_pool_keys(pair_address)
        if pool_keys is None:
            cprint("No pool keys found...", "red", attrs=["bold", "reverse"])
            return None, False
        cprint("Pool keys fetched successfully.", "white", "on_green", attrs=["bold"])

        mint = pool_keys['base_mint'] if str(pool_keys['base_mint']) != SOL else pool_keys['quote_mint']
        
        cprint("Calculating transaction amounts...", "blue", attrs=["bold"])
        amount_in = int(sol_in * SOL_DECIMAL)
        token_price, token_decimal = get_token_price(pool_keys)
        amount_out = float(sol_in) / float(token_price)
        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * 10**token_decimal)
        logging.info(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}")
        cprint(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}", "yellow", attrs=["bold"])


        cprint("Checking for existing token account...", "cyan", attrs=["bold"])
        token_account_check = client.get_token_accounts_by_owner(payer_keypair.pubkey(), TokenAccountOpts(mint), Processed)
        if token_account_check.value:
            token_account = token_account_check.value[0].pubkey
            token_account_instr = None
            cprint("Token account found.", "white", "on_green", attrs=["bold"])
        else:
            token_account = get_associated_token_address(payer_keypair.pubkey(), mint)
            token_account_instr = create_associated_token_account(payer_keypair.pubkey(), payer_keypair.pubkey(), mint)
            logging.info("No existing token account found; creating associated token account.")
            cprint("No existing token account found; creating associated token account.", "magenta", attrs=["bold", "reverse"])

        cprint("Generating seed for WSOL account...", "green", attrs=["bold"])
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode('utf-8') 
        wsol_token_account = Pubkey.create_with_seed(payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
        balance_needed = Token.get_min_balance_rent_for_exempt_for_account(client)
        
        cprint("Creating and initializing WSOL account...", "blue", attrs=["bold"])
        create_wsol_account_instr = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=int(balance_needed + amount_in),
                space=ACCOUNT_LAYOUT.sizeof(),
                owner=TOKEN_PROGRAM_ID
            )
        )
        
        init_wsol_account_instr = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey()
            )
        )
        
        cprint("Funding WSOL account...", "yellow", attrs=["bold"])
        fund_wsol_account_instr = transfer(
            TransferParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                lamports=int(amount_in)
            )
        )

        cprint("Creating swap instructions...", "green", attrs=["bold"])
        swap_instructions = make_swap_instruction(amount_in, minimum_amount_out, wsol_token_account, token_account, pool_keys, payer_keypair)

        cprint("Preparing to close WSOL account after swap...", "blue", attrs=["bold"])
        close_wsol_account_instr = close_account(CloseAccountParams(TOKEN_PROGRAM_ID, wsol_token_account, payer_keypair.pubkey(), payer_keypair.pubkey()))
        
        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(UNIT_PRICE),
            create_wsol_account_instr,
            init_wsol_account_instr,
            fund_wsol_account_instr
        ]
        
        if token_account_instr:
            instructions.append(token_account_instr)
        
        instructions.append(swap_instructions)
        instructions.append(close_wsol_account_instr)

        cprint("Compiling transaction message...", "yellow", attrs=["bold"])
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],
            client.get_latest_blockhash().value.blockhash,
        )

        cprint("Sending transaction...", "cyan", attrs=["bold"])
        txn_sig = client.send_transaction(
            txn = VersionedTransaction(compiled_message, [payer_keypair]), 
            opts = TxOpts(skip_preflight=True)
            ).value
        
        logging.info(f"Transaction Signature: {txn_sig}")

        cprint("Confirming transaction...", "white", attrs=["bold"])
        confirmed = confirm_txn(txn_sig)
        logging.info(colored(f"Transaction confirmed: {confirmed}", "white", "on_light_green", attrs=["bold"]))
        cprint(f"Link to transaction in explorer : https://explorer.solana.com/tx/{txn_sig}", "magenta", "on_white")
        
        return (txn_sig, confirmed)

    except Exception as e:
        logging.error(colored(f"Error occurred during transaction: {str(e)}", "red", attrs=["bold", "reverse"]))
        return (None, False)

def sell(pair_address: str, percentage: int = 100, slippage: int = 5) -> bool:
    try:
        cprint(f"Starting sell transaction for pair address: {pair_address}", "yellow", "on_blue", attrs=["bold"])
        if not (1 <= percentage <= 100):
            cprint("Percentage must be between 1 and 100.", "magenta", attrs=["bold", "reverse"])
            return False

        cprint("Fetching pool keys...", "green", attrs=["bold"])
        pool_keys = fetch_pool_keys(pair_address)
        if pool_keys is None:
            cprint("No pool keys found...", "red", attrs=["bold", "reverse"])
            return False
        cprint("Pool keys fetched successfully.", "white", "on_light_green", attrs=['bold'])

        mint = pool_keys['base_mint'] if str(pool_keys['base_mint']) != SOL else pool_keys['quote_mint']
        
        cprint("Retrieving token balance...", "blue", attrs=["bold"])
        token_balance = get_token_balance(str(mint))
        cprint("Token Balance: {token_balance}", "light_yellow", attrs=["bold"]) 
        if token_balance == 0:
            cprint("No token balance available to sell.", "red", attrs=["bold", "reverse"])
            return False
        token_balance = token_balance * (percentage / 100)
        cprint(f"Selling {percentage}% of the token balance, adjusted balance: {token_balance}", "green", attrs=["bold"])

        cprint("Calculating transaction amounts...", "blue", attrs=["bold"])
        token_price, token_decimal = get_token_price(pool_keys)
        amount_out = float(token_balance) * float(token_price)
        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * SOL_DECIMAL)
        amount_in = int(token_balance * 10**token_decimal)
        cprint(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}", "magenta")

        token_account = get_associated_token_address(payer_keypair.pubkey(), mint)

        cprint("Generating seed and creating WSOL account...", "cyan", attrs=["bold"])
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode('utf-8')
        wsol_token_account = Pubkey.create_with_seed(payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
        balance_needed = Token.get_min_balance_rent_for_exempt_for_account(client)
        
        create_wsol_account_instr = create_account_with_seed(
            CreateAccountWithSeedParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                base=payer_keypair.pubkey(),
                seed=seed,
                lamports=int(balance_needed),
                space=ACCOUNT_LAYOUT.sizeof(),
                owner=TOKEN_PROGRAM_ID
            )
        )
        
        init_wsol_account_instr = initialize_account(
            InitializeAccountParams(
                program_id=TOKEN_PROGRAM_ID,
                account=wsol_token_account,
                mint=WSOL,
                owner=payer_keypair.pubkey()
            )
        )

        cprint("Creating swap instructions...", "light_yellow")
        swap_instructions = make_swap_instruction(amount_in, minimum_amount_out, token_account, wsol_token_account, pool_keys, payer_keypair)
        
        cprint("Preparing to close WSOL account after swap...", "light_cyan", attrs=["bold"])
        close_wsol_account_instr = close_account(CloseAccountParams(TOKEN_PROGRAM_ID, wsol_token_account, payer_keypair.pubkey(), payer_keypair.pubkey()))
        
        instructions = [
            set_compute_unit_limit(UNIT_BUDGET),
            set_compute_unit_price(UNIT_PRICE),
            create_wsol_account_instr,
            init_wsol_account_instr,
            swap_instructions,
            close_wsol_account_instr
        ]
        
        if percentage == 100:
            cprint("Preparing to close token account after swap...", "light_yellow", attrs=["bold"])
            close_token_account_instr = close_account(
                CloseAccountParams(TOKEN_PROGRAM_ID, token_account, payer_keypair.pubkey(), payer_keypair.pubkey())
            )
            instructions.append(close_token_account_instr)

        logging.info(colored("Compiling transaction message...", "green", attrs=["bold"]))
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],  
            client.get_latest_blockhash().value.blockhash,
        )

        cprint("Sending transaction...", "light_blue", attrs=["bold"])
        txn_sig = client.send_transaction(
            txn = VersionedTransaction(compiled_message, [payer_keypair]), 
            opts = TxOpts(skip_preflight=True)
            ).value
        
        cprint(f"Transaction Signature: {txn_sig}", "light_grey", attrs=["bold"])

        cprint("Confirming transaction...", "cyan", attrs=["bold"])
        confirmed = confirm_txn(txn_sig)
        cprint(f"Transaction confirmed: {confirmed}", "white", "on_light_green", attrs=["bold"])

        cprint(f"Link to transaction in explorer : https://explorer.solana.com/tx/{txn_sig}", "magenta", "on_white")
        
        return confirmed, txn_sig
    
    except Exception as e:
        cprint(f"Error occurred during transaction: {str(e)}", "red", attrs=["bold", "reverse"])
        return False, None

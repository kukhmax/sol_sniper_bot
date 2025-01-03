import base64
import os

from solana.rpc.commitment import Processed
from solana.rpc.types import TokenAccountOpts, TxOpts

from solders.compute_budget import (  # type: ignore
    set_compute_unit_limit, set_compute_unit_price 
)
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

from app.config import client, payer_keypair, UNIT_BUDGET, UNIT_PRICE
from app.constants import SOL_DECIMAL, SOL, TOKEN_PROGRAM_ID, WSOL
from app.layouts import ACCOUNT_LAYOUT
from app.utils import confirm_txn, fetch_pool_keys, get_token_price, make_swap_instruction, get_token_balance



def buy(pair_address: str, pool_keys=None, sol_in: float = .01, slippage: int = 5, token_symbol=None):
    try:
        # cprint(f"Starting buy transaction for pair address: {pair_address}", "yellow", "on_blue", attrs=["bold"])
        logging.debug(f"Starting buy transaction for pair address: {pair_address}")

        if pool_keys is None:        
            # cprint("Fetching pool keys...", "green", attrs=["bold"])
            pool_keys = fetch_pool_keys(pair_address)

            if pool_keys is None:
                # cprint("No pool keys found...", "red", attrs=["bold", "reverse"])
                logging.error("No pool keys found...")
                return None, False
            # cprint("Pool keys fetched successfully.", "white", "on_green", attrs=["bold"])
            logging.debug(f"  Pool keys for    {token_symbol}    fetched successfully.")

        mint = pool_keys['base_mint'] if str(pool_keys['base_mint']) != SOL else pool_keys['quote_mint']
        
        # cprint("Calculating transaction amounts...", "blue", attrs=["bold"])
        logging.debug("Calculating transaction amounts...")
        amount_in = int(sol_in * SOL_DECIMAL)
        token_price, token_decimal = get_token_price(pool_keys)
        amount_out = float(sol_in) / float(token_price)
        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * 10**token_decimal)
        # logging.info(f"                                       Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}")
        cprint(f"\n{token_symbol}   Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}", "yellow", attrs=["bold"])


        # cprint("Checking for existing token account...", "cyan", attrs=["bold"])
        logging.debug("Checking for existing token account...")
        token_account_check = client.get_token_accounts_by_owner(payer_keypair.pubkey(), TokenAccountOpts(mint), Processed)
        if token_account_check.value:
            token_account = token_account_check.value[0].pubkey
            token_account_instr = None
            # cprint("Token account found.", "white", "on_green", attrs=["bold"])
            logging.info(f"\n      {token_symbol}      Token account found: {token_account}")
        else:
            token_account = get_associated_token_address(payer_keypair.pubkey(), mint)
            token_account_instr = create_associated_token_account(payer_keypair.pubkey(), payer_keypair.pubkey(), mint)
            logging.error("No existing token account found; creating associated token account.")
            # cprint("No existing token account found; creating associated token account.", "magenta", attrs=["bold", "reverse"])

        # cprint("Generating seed for WSOL account...", "green", attrs=["bold"])
        logging.debug("Generating seed for WSOL account...")
        seed = base64.urlsafe_b64encode(os.urandom(24)).decode('utf-8') 
        wsol_token_account = Pubkey.create_with_seed(payer_keypair.pubkey(), seed, TOKEN_PROGRAM_ID)
        balance_needed = Token.get_min_balance_rent_for_exempt_for_account(client)
        
        # cprint("Creating and initializing WSOL account...", "blue", attrs=["bold"])
        logging.debug("Creating and initializing WSOL account...")
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

        # cprint("Funding WSOL account...", "yellow", attrs=["bold"])
        logging.debug("Funding WSOL account...")
        fund_wsol_account_instr = transfer(
            TransferParams(
                from_pubkey=payer_keypair.pubkey(),
                to_pubkey=wsol_token_account,
                lamports=int(amount_in)
            )
        )

        # cprint("Creating swap instructions...", "green", attrs=["bold"])
        logging.debug(f"     {token_symbol}      Creating swap instructions...")
        swap_instructions = make_swap_instruction(amount_in, minimum_amount_out, wsol_token_account, token_account, pool_keys, payer_keypair)

        # cprint("Preparing to close WSOL account after swap...", "blue", attrs=["bold"])
        logging.debug("Preparing to close WSOL account after swap...")
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

        # cprint("Compiling transaction message...", "yellow", attrs=["bold"])
        logging.debug(f"     {token_symbol}     Compiling transaction message...")
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],
            client.get_latest_blockhash().value.blockhash,
        )

        # cprint("Sending transaction...", "cyan", attrs=["bold"])
        logging.debug("    {token_symbol}     Sending transaction...")
        txn_sig = client.send_transaction(
            txn = VersionedTransaction(compiled_message, [payer_keypair]), 
            opts = TxOpts(skip_preflight=True)
            ).value

        logging.info(f"Transaction Signature: {txn_sig}")

        # cprint("Confirming transaction...", "white", attrs=["bold"])
        logging.debug(f"    {token_symbol}  -   Confirming transaction...")
        confirmed = confirm_txn(txn_sig)
        logging.info(f"\n    {token_symbol}  -  Transaction confirmed: {confirmed}")

        return (txn_sig, confirmed)

    except Exception as e:
        logging.error(f"  {token_symbol} - Error occurred during transaction: {str(e)}")
        return (None, False)

def sell(pair_address: str, percentage: int = 100, slippage: int = 5, token_symbol=""):
    """
    Executes a sell transaction for a specified percentage of tokens in a given trading pair.

    Args:
        pair_address (str): The address of the trading pair to sell tokens on.
        percentage (int, optional): The percentage of the token balance to sell. Must be between 1 and 100. Defaults to 100.
        slippage (int, optional): The allowable slippage percentage for the transaction. Defaults to 5.

    Returns:
        bool: True if the transaction is successful and confirmed, False otherwise.

    The function performs the following steps:
    - Validates the percentage to ensure it's within the acceptable range.
    - Fetches the pool keys for the specified pair address.
    - Retrieves the token balance and calculates the amounts for the transaction based on the current token price and slippage.
    - Generates swap instructions and manages token accounts, including WSOL account creation and closure.
    - Sends the transaction and confirms its success.
    - Handles errors by logging them and returning False if the transaction fails.
    """

    try:
        # cprint(f"Starting sell transaction for pair address: {pair_address}", "yellow", "on_blue", attrs=["bold"])
        logging.debug(f"Starting sell transaction for: {token_symbol}")
        if not (1 <= percentage <= 100):
            # cprint("Percentage must be between 1 and 100.", "magenta", attrs=["bold", "reverse"])
            logging.error("Percentage must be between 1 and 100.")
            return False, None, None

        # cprint("Fetching pool keys...", "green", attrs=["bold"])
        logging.debug("  {token_symbol}  -  Fetching pool keys...")
        pool_keys = fetch_pool_keys(pair_address)
        if pool_keys is None:
            # cprint("No pool keys found...", "red", attrs=["bold", "reverse"])
            logging.error("  {token_symbol}  -  No pool keys found...")
            return False, None, None
        # cprint("Pool keys fetched successfully.", "white", "on_light_green", attrs=['bold'])
        logging.debug("  {token_symbol}  -   Pool keys fetched successfully.")

        mint = pool_keys['base_mint'] if str(pool_keys['base_mint']) != SOL else pool_keys['quote_mint']

        # cprint("Retrieving token balance...", "blue", attrs=["bold"])
        logging.debug("  {token_symbol}  -  Retrieving token balance...")
        token_balance = get_token_balance(str(mint))
        # cprint(f"Token Balance: {token_balance}", "light_yellow", attrs=["bold"])
        logging.info(f"\n    {token_symbol}  -   Token Balance: {token_balance}")
        if token_balance == 0:
            # cprint("No token balance available to sell.", "red", attrs=["bold", "reverse"])
            logging.error("   {token_symbol}  -   No token balance available to sell.")
            return False, None, None
        token_balance = token_balance * (percentage / 100)
        # cprint(f"Selling {percentage}% of the token balance, adjusted balance: {token_balance}", "green", attrs=["bold"])
        logging.debug(f"\n   {token_symbol}  -   Selling {percentage}% of the token balance, adjusted balance: {token_balance}")

        # cprint("Calculating transaction amounts...", "blue", attrs=["bold"])
        logging.debug("Calculating transaction amounts...")
        token_price, token_decimal = get_token_price(pool_keys)
        amount_out = float(token_balance) * float(token_price)
        slippage_adjustment = 1 - (slippage / 100)
        amount_out_with_slippage = amount_out * slippage_adjustment
        minimum_amount_out = int(amount_out_with_slippage * SOL_DECIMAL)
        amount_in = int(token_balance * 10**token_decimal)
        # cprint(f"Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}", "magenta")
        logging.info(f"\n    {token_symbol}  -  Amount In: {amount_in} | Minimum Amount Out: {minimum_amount_out}")

        token_account = get_associated_token_address(payer_keypair.pubkey(), mint)

        # cprint("Generating seed and creating WSOL account...", "cyan", attrs=["bold"])
        logging.debug("Generating seed and creating WSOL account...")
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

        # cprint("Creating swap instructions...", "light_yellow")
        logging.debug("Creating swap instructions...")
        swap_instructions = make_swap_instruction(amount_in, minimum_amount_out, token_account, wsol_token_account, pool_keys, payer_keypair)
        
        # cprint("Preparing to close WSOL account after swap...", "light_cyan", attrs=["bold"])
        logging.debug("Preparing to close WSOL account after swap...")
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
            # cprint("Preparing to close token account after swap...", "light_yellow", attrs=["bold"])
            logging.debug("Preparing to close token account after swap...")
            close_token_account_instr = close_account(
                CloseAccountParams(TOKEN_PROGRAM_ID, token_account, payer_keypair.pubkey(), payer_keypair.pubkey())
            )
            instructions.append(close_token_account_instr)

        logging.debug("--  {token_symbol} -- Compiling transaction message...")
        compiled_message = MessageV0.try_compile(
            payer_keypair.pubkey(),
            instructions,
            [],
            client.get_latest_blockhash().value.blockhash,
        )

        # cprint("Sending transaction...", "light_blue", attrs=["bold"])
        logging.debug("  {token_symbol}  -  Sending transaction...")
        txn_sig = client.send_transaction(
            txn = VersionedTransaction(compiled_message, [payer_keypair]), 
            opts = TxOpts(skip_preflight=True)
            ).value

        # cprint(f"Transaction Signature: {txn_sig}", "light_grey", attrs=["bold"])
        logging.info(f"  {token_symbol}  -  Transaction Signature: {txn_sig}")

        # cprint("Confirming transaction...", "cyan", attrs=["bold"])
        logging.debug("  {token_symbol}  -  Confirming transaction...")
        confirmed = confirm_txn(txn_sig, token_symbol)
        # cprint(f"Transaction confirmed: {confirmed}", "white", "on_light_green", attrs=["bold"])
        logging.info(f"--   {token_symbol}  -   Transaction confirmed: {confirmed}")
        return confirmed, txn_sig, token_balance

    except Exception as e:
        # cprint(f"Error occurred during transaction: {str(e)}", "red", attrs=["bold", "reverse"])
        logging.error(f"  {token_symbol}  -  Error occurred during transaction: {str(e)}")
        return False, None, None

Обновленный main.py с данными из веб-сокета

import os
import json
from dotenv import load_dotenv
from solana.rpc.api import Client
from spl.token.client import Token
from solders.pubkey import Pubkey
from solders.keypair import Keypair  
from spl.token.core import _TokenCore
from solana.rpc.commitment import Commitment
from spl.token.instructions import close_account, CloseAccountParams

from termcolor import colored, cprint

from utils import Pool


load_dotenv()

RPC_URL, PRIVATE_KEY = os.getenv("RPC_URL"), os.getenv("PRIVATE_KEY")

client = Client(RPC_URL)
pool = Pool(Client)

TOKEN = "" # Token program ID
PAYER = Keypair.from_base58_string(PRIVATE_KEY)
TOKEN_MINT = Pubkey.from_string(TOKEN)

AMOUNT = 0.001 # Amount in SOL
LAMPPORTS_PER_SOL = 1_000_000_000

amount_in = float(AMOUNT * LAMPPORTS_PER_SOL)
pool_keys = pool.get_pool_keys(str(TOKEN_MINT))  # получает ключи пула для заданного токена

#  Получаем информацию о программе токена и сохраняет ее владельца.
cprint("1. Get TOKEN_PROGRAM_ID ...", "green", "on_yellow", attrs=["bold"])
account_program_id = client.get_account_info_json_parsed(TOKEN_MINT)
TOKEN_OWNER = account_program_id.value.owner

# Получает адрес ассоциированного токен-аккаунта и инструкции для его создания, если он не существует.
cprint("2. Get Mint TOken accounts addresses ...", "blue", "on_white", attrs=["bold"])
swap_associated_token_address, swap_token_account_instructions = get_token_account(
    client, PAYER.pubkey(), TOKEN_MINT
)




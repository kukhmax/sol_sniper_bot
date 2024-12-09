import os
import base58
from solana.rpc.api import Client
from solders.keypair import Keypair #type: ignore

SECRET_KEY = os.getenv("PRIVATE_KEY")
RPC = "https://mainnet.helius-rpc.com/?api-key=16f6afbc-1edf-4ba5-b482-f1bdde284062"
MAIN_RPC = "https://api.mainnet-beta.solana.com"
UNIT_BUDGET =  100_000
UNIT_PRICE =  1_000_000
client = Client(RPC)
# payer_keypair = Keypair.from_base58_string(PRIV_KEY)
payer_keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))




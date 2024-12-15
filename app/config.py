import os
import base58
from solana.rpc.api import Client
from solders.keypair import Keypair  # type: ignore

SECRET_KEY = os.getenv("PRIVATE_KEY")
RPC = "https://mainnet.helius-rpc.com/?api-key=59119b1f-66d8-47dd-be0f-f1e7ced1916d"  # ignore E501
MAIN_RPC = "https://api.mainnet-beta.solana.com"
UNIT_BUDGET = 100_000
UNIT_PRICE = 1_000_000
client = Client(RPC)
# payer_keypair = Keypair.from_base58_string(PRIV_KEY)
payer_keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))

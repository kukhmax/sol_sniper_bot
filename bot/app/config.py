import os
import base58
from solana.rpc.api import Client
from solders.keypair import Keypair  # type: ignore
import dotenv

dotenv.load_dotenv()

SECRET_KEY = os.getenv("PRIVATE_KEY")
RPC = "https://mainnet.helius-rpc.com/?api-key=bf911a9e-fd0e-42be-aece-f32bf257ec63"  # ignore E501
MAIN_RPC = "https://api.mainnet-beta.solana.com"
UNIT_BUDGET = 100_000
UNIT_PRICE = 1_000_000
client = Client(RPC)
# payer_keypair = Keypair.from_base58_string(PRIV_KEY)
payer_keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))

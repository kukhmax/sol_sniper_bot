import os
import json
import base58
import time
from functools import wraps
from termcolor import colored, cprint

from solders.pubkey import Pubkey
from solana.rpc.types import TokenAccountOpts
from solders.keypair import Keypair
from solana.rpc.api import Client
from solana.exceptions import SolanaRpcException


def handle_rate_limiting(retry_attempts=3, retry_delay=10):
    def decorator(client_function):
        @wraps(client_function)
        def wrapper(*args, **kwargs):
            for _ in range(retry_attempts):
                try:
                    return client_function(*args, **kwargs)
                except SolanaRpcException as e:
                    if 'HTTPStatusError' in e.error_msg:
                        cprint(f"Rate limit exceeded in {client_function.__name__}, retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                    else:
                        raise
            cprint("Rate limit error persisting, skipping this iteration.", "yellow", "on_cyan")
            return None

        return wrapper

    return decorator

class Config:
    def __init__(self, path):
        self.path = path
        self.api_key = None
        self.private_key = None
        self.custom_rpc_https = None
        self.usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        self.sol_mint = "So11111111111111111111111111111111111111112"
        self.other_mint = None
        self.other_mint_symbol = None
        self.price_update_seconds = None
        self.trading_interval_minutes = None
        self.slippage = None  # BPS
        self.computeUnitPriceMicroLamports = None
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.path):
            cprint(
                "Soltrade was unable to detect the JSON file. Are you sure config.json has not been renamed or removed?", "red", attrs=["reverse", "blink"])
            exit(1)

        with open(self.path, 'r') as file:
            try:
                config_data = json.load(file)
                self.api_key = config_data["api_key"]
                self.private_key = config_data["private_key"]
                self.custom_rpc_https = config_data.get("custom_rpc_https") or "https://api.mainnet-beta.solana.com/"
                self.other_mint = config_data.get("other_mint", "")
                self.other_mint_symbol = config_data.get("other_mint_symbol", "UNKNOWN")
                self.price_update_seconds = int(config_data.get("price_update_seconds", 60))
                self.trading_interval_minutes = int(config_data.get("trading_interval_minutes", 1))
                self.slippage = int(config_data.get("slippage", 50))
                self.computeUnitPriceMicroLamports = int(config_data.get("computeUnitPriceMicroLamports", 20 * 14000))  # default fee of roughly $.04 today
            except json.JSONDecodeError as e:
                cprint(f"Error parsing JSON: {e}", "red", attrs=["reverse", "blink"])
                exit(1)
            except KeyError as e:
                cprint(f"Missing configuration key: {e}", "red", attrs=["reverse", "blink"])
                exit(1)

    @property
    def keypair(self) -> Keypair:
        try:
            return Keypair.from_bytes(base58.b58decode(self.private_key))
        except Exception as e:
            cprint(f"Error decoding private key: {e}", "red", attrs=["reverse", "blink"])
            exit(1)

    @property
    def public_address(self) -> Pubkey:
        return self.keypair.pubkey()

    @property
    def client(self) -> Client:
        rpc_url = self.custom_rpc_https
        return Client(rpc_url)
    
    @property
    def decimals(self) -> int:
        response = self.client.get_account_info_json_parsed(Pubkey.from_string(config().other_mint)).to_json()
        json_response = json.loads(response)
        value = 10**json_response["result"]["value"]["data"]["parsed"]["info"]["decimals"]
        return value


_config_instance = None


def config(path=None) -> Config:
    global _config_instance
    if _config_instance is None and path is not None:
        _config_instance = Config(path)
    return _config_instance

# Returns the current balance of token in the wallet
@handle_rate_limiting()
def find_balance(token_mint: str) -> float:
    if token_mint == config().sol_mint:
        balance_response = config().client.get_balance(config().public_address).value
        balance_response = balance_response / (10 ** 9)
        return balance_response

    response = config().client.get_token_accounts_by_owner_json_parsed(config().public_address, TokenAccountOpts(
        mint=Pubkey.from_string(token_mint))).to_json()
    json_response = json.loads(response)
    if len(json_response["result"]["value"]) == 0:
        return 0
    return json_response["result"]["value"][0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]




from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey # type: ignore
from solana.transaction import Transaction, TransactionInstruction, AccountMeta
from solders.system_program import TransferParams, transfer
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import create_associated_token_account_instruction, get_associated_token_address
from spl.token.instructions import sync_native
from anchorpy import Program, Provider, Wallet
import asyncio
import json
import os
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional
import logging

# Константы
LAMPORTS_PER_SOL = 1000000000
MAINNET_PROGRAM_ID = {
    "AmmV4": Pubkey("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"),
    "OPENBOOK_MARKET": Pubkey("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX")
}

@dataclass
class PoolKeys:
    id: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    lp_mint: Pubkey
    base_decimals: int
    quote_decimals: int
    lp_decimals: int
    version: int
    program_id: Pubkey
    authority: Pubkey
    open_orders: Pubkey
    target_orders: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey
    withdraw_queue: Pubkey
    lp_vault: Pubkey
    market_version: int
    market_program_id: Pubkey
    market_id: Pubkey
    market_authority: Pubkey
    market_base_vault: Pubkey
    market_quote_vault: Pubkey
    market_bids: Pubkey
    market_asks: Pubkey
    market_event_queue: Pubkey

class SolanaSniperBot:
    def __init__(self, rpc_url: str, wallet_keypair: Wallet):
        self.connection = AsyncClient(rpc_url)
        self.wallet = wallet_keypair
        self.provider = Provider(self.connection, self.wallet)
        
        # Настройки бота
        self.settings = {
            "purchase_amount_sol": 0.1,
            "buy_compute_limit": 200_000,
            "buy_unit_price_fee": 1000
        }
        
        # Путь для сохранения данных
        self.data_path = os.path.join(os.path.dirname(__file__), 'sniper_data', 'bought_tokens.json')
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

    async def monitor_new_tokens(self):
        logging.info('Monitoring new Solana tokens...')
        
        try:
            async for log_data in self.connection.logs_subscribe():
                try:
                    await self._process_log(log_data)
                except Exception as e:
                    logging.error(f"Error processing log: {e}")
                    
        except Exception as e:
            logging.error(f"Error in monitor_new_tokens: {e}")

    async def _process_log(self, log_data):
        if log_data.err:
            return

        signature = log_data.signature
        logging.info(f'Found new token signature: {signature}')

        tx = await self.connection.get_transaction(signature)
        if not tx or tx.get('meta', {}).get('err'):
            return

        # Извлекаем инструкции и ищем создание пула
        instructions = tx['transaction']['message']['instructions']
        pool_creation_instruction = next(
            (instr for instr in instructions 
             if Pubkey(instr['programId']) == MAINNET_PROGRAM_ID["AmmV4"]),
            None
        )

        if not pool_creation_instruction:
            return

        pool_address = Pubkey(pool_creation_instruction['accounts'][4])
        pool_keys = await self._get_pool_keys(pool_address)
        
        if pool_keys:
            await self._snipe_token(pool_keys)

    async def _get_pool_keys(self, pool_address: Pubkey) -> Optional[PoolKeys]:
        try:
            pool_account = await self.connection.get_account_info(pool_address)
            if not pool_account:
                return None
            
            # Здесь должна быть логика декодирования данных пула
            # В Python это сложнее, чем в TypeScript, так как нужно самостоятельно
            # реализовывать декодирование байтов аккаунта
            
            # Для примера возвращаем заглушку
            return PoolKeys(
                id=pool_address,
                base_mint=Pubkey("11111111111111111111111111111111"),
                quote_mint=Pubkey("So11111111111111111111111111111111111111112"),
                # ... остальные поля
            )

        except Exception as e:
            logging.error(f"Error getting pool keys: {e}")
            return None

    async def _snipe_token(self, pool_keys: PoolKeys):
        try:
            # Создаем транзакцию
            transaction = Transaction()
            
            # Добавляем инструкции для установки лимитов
            transaction.add(
                self._create_compute_budget_instruction(
                    self.settings["buy_compute_limit"],
                    self.settings["buy_unit_price_fee"]
                )
            )
            
            # Создаем аккаунты токенов и добавляем инструкции свапа
            wsol_account = get_associated_token_address(
                self.wallet.public_key,
                Pubkey("So11111111111111111111111111111111111111112")
            )
            
            transaction.add(
                create_associated_token_account_instruction(
                    payer=self.wallet.public_key,
                    owner=self.wallet.public_key,
                    mint=Pubkey("So11111111111111111111111111111111111111112")
                )
            )
            
            # Добавляем трансфер SOL
            transaction.add(
                transfer(TransferParams(
                    from_pubkey=self.wallet.public_key,
                    to_pubkey=wsol_account,
                    lamports=int(self.settings["purchase_amount_sol"] * LAMPORTS_PER_SOL)
                ))
            )
            
            # Добавляем синхронизацию wrapped SOL
            transaction.add(sync_native(wsol_account))
            
            # Здесь должны быть инструкции для свапа через Raydium
            # Это сложная часть, которая требует специфических инструкций Raydium
            
            # Отправляем транзакцию
            result = await self.provider.send(transaction)
            logging.info(f"Swap successful: {result}")
            
            return result
            
        except Exception as e:
            logging.error(f"Error in snipe_token: {e}")
            return None

    def _create_compute_budget_instruction(self, units: int, micro_lamports: int) -> TransactionInstruction:
        # Создаем инструкцию для установки бюджета вычислений
        return TransactionInstruction(
            program_id=Pubkey("ComputeBudget111111111111111111111111111111"),
            keys=[],
            data=bytes([])  # Здесь должны быть закодированные данные
        )

async def main():
    # Инициализация и запуск бота
    bot = SolanaSniperBot(
        rpc_url="https://api.mainnet-beta.solana.com",
        wallet_keypair=Wallet.local()  # Предполагается, что кошелек настроен
    )
    
    await bot.monitor_new_tokens()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
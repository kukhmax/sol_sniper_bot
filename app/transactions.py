import os
import time
import random
import base58
import base64
import struct
import logging
import backoff
from solana.rpc.types import TxOpts
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed, Finalized
from solana.exceptions import SolanaRpcException
from solders.pubkey import Pubkey  # type: ignore
from solders.keypair import Keypair  # type: ignore
from solders.system_program import transfer, TransferParams
from solders.transaction import Transaction  # type: ignore
from solders.message import Message  # type: ignore
from solders.instruction import Instruction, AccountMeta  # type: ignore
from solders.hash import Hash  # type: ignore
from httpx import HTTPStatusError
from typing import Optional, Tuple, Callable, Any
from termcolor import colored, cprint

# Configure logging
logging.basicConfig(
    filename='swap.log',
    filemode='a',
    level=logging.DEBUG, 
    format="%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]",
)

class RaydiumSwap:
    RAYDIUM_V4_PROGRAM_ID = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
    ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
    SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
    WSOL_MINT = "So11111111111111111111111111111111111111112"
    SYSVAR_RENT_PUBKEY = "SysvarRent111111111111111111111111111111111"
    
    # Expanded list of RPC endpoints with health check
    RPC_ENDPOINTS = [
        "https://api.mainnet-beta.solana.com",
        "https://rpc.ankr.com/solana",
        "https://solana-mainnet.rpc.extrnode.com",
    ]
    
    def __init__(self, private_key: str):
        """Initialize RaydiumSwap with wallet private key"""
        self.current_rpc_index = 0
        self.healthy_endpoints = []
        self._init_healthy_endpoints()  # Changed to not return value
        
        if not self.healthy_endpoints:
            # Fallback to first endpoint if no healthy ones found
            self.healthy_endpoints = [self.RPC_ENDPOINTS[0]]
            logging.warning("No healthy endpoints found, falling back to primary endpoint")
            
        self.client = self._create_client()
        self.wallet = Keypair.from_bytes(base58.b58decode(private_key))
        self.program_id = Pubkey.from_string(self.RAYDIUM_V4_PROGRAM_ID)
        self.token_program_id = Pubkey.from_string(self.TOKEN_PROGRAM_ID)
        self.associated_token_program_id = Pubkey.from_string(self.ASSOCIATED_TOKEN_PROGRAM_ID)
        self.token_program_id = Pubkey.from_string(self.TOKEN_PROGRAM_ID)
        self.system_program_id = Pubkey.from_string(self.SYSTEM_PROGRAM_ID)
        self.sysvar_rent_pubkey = Pubkey.from_string(self.SYSVAR_RENT_PUBKEY)


    def _init_healthy_endpoints(self) -> None:
        """Initialize list of healthy RPC endpoints with improved error handling"""
        for endpoint in self.RPC_ENDPOINTS:
            try:
                client = Client(endpoint)
                # Use a more basic health check
                try:
                    # First try getting recent blockhash as it's more reliable
                    client.get_latest_blockhash()
                except Exception:
                    # Fallback to get_health
                    health_result = client._provider.make_request(
                        {"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
                        lambda x: x
                    )
                    if not isinstance(health_result, dict) or health_result.get("result") != "ok":
                        raise Exception("Unhealthy endpoint")

                self.healthy_endpoints.append(endpoint)
                logging.info(f"RPC endpoint {endpoint} is healthy")
                
            except Exception as e:
                logging.warning(f"RPC endpoint {endpoint} failed health check: {str(e)}")
                continue
            
            # Break if we found at least one healthy endpoint
            if len(self.healthy_endpoints) > 0:
                break

    def _execute_with_retry(self, func: Callable[[], Any]) -> Any:
        """Execute function with improved exponential backoff retry and error handling"""
        @backoff.on_exception(
            backoff.expo,
            (HTTPStatusError, SolanaRpcException),
            max_tries=5,
            max_time=30,
            jitter=backoff.full_jitter,  # Add jitter to prevent thundering herd
            on_backoff=lambda details: logging.info(
                f"Retrying RPC call. Attempt {details['tries']}/5"
            )
        )
        def _execute():
            try:
                return func()
            except (HTTPStatusError, SolanaRpcException) as e:
                if isinstance(e, HTTPStatusError) and e.response.status_code in [429, 500, 503]:
                    self._rotate_rpc_endpoint()
                raise
        return _execute()

    def _create_client(self) -> Client:
        """Create a new client with the current RPC endpoint"""
        if not self.healthy_endpoints:
            raise ValueError("No healthy RPC endpoints available")
        
        endpoint = self.healthy_endpoints[self.current_rpc_index]
        try:
            return Client(endpoint, commitment=Confirmed)
        except Exception as e:
            logging.error(f"Failed to create client for endpoint {endpoint}: {str(e)}")
            self._rotate_rpc_endpoint()
            return Client(self.healthy_endpoints[self.current_rpc_index], commitment=Confirmed)

    def _rotate_rpc_endpoint(self) -> None:
        """Rotate to next healthy RPC endpoint with validation"""
        if not self.healthy_endpoints:
            raise ValueError("No healthy RPC endpoints available")
            
        previous_endpoint = self.healthy_endpoints[self.current_rpc_index]
        self.current_rpc_index = (self.current_rpc_index + 1) % len(self.healthy_endpoints)
        
        try:
            self.client = self._create_client()
            logging.info(f"Switched from {previous_endpoint} to {self.healthy_endpoints[self.current_rpc_index]}")
            cprint(f"Switched RPC endpoint", "yellow", "on_red")
        except Exception as e:
            logging.error(f"Failed to rotate RPC endpoint: {str(e)}")
            # Remove the failing endpoint and try the next one
            self.healthy_endpoints.pop(self.current_rpc_index)
            if self.healthy_endpoints:
                self.current_rpc_index = 0
                self.client = self._create_client()
            else:
                raise ValueError("No remaining healthy RPC endpoints")

    def get_token_account_info(self, token_account: Pubkey) -> Optional[dict]:
        """Get token account information"""
        try:
            account_info = self.client.get_account_info(token_account, commitment=Confirmed)
            if account_info.value:
                return account_info.value
            return None
        except Exception as e:
            logging.error(f"Error getting token account info: {str(e)}")
            return None

    def find_associated_token_address(self, owner: Pubkey, token_mint: Pubkey) -> Pubkey:
        """Find the associated token account address for a given wallet and token mint"""
        seeds = [
            bytes(owner),
            bytes(self.token_program_id),
            bytes(token_mint)
        ]
        
        # Create PDA
        address, _ = Pubkey.find_program_address(
            seeds,
            self.associated_token_program_id
        )
        return address

    def create_associated_token_account_ix(
        self,
        payer: Pubkey,
        owner: Pubkey,
        mint: Pubkey
    ) -> Instruction:
        """Create instruction to create an associated token account"""
        # Get the PDA for the associated token account
        associated_token_address = self.find_associated_token_address(owner, mint)

        # Проверка на совпадение program_id для Associated Token Program
        if str(self.associated_token_program_id) != "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL":
            raise ValueError("Некорректный ASSOCIATED_TOKEN_PROGRAM_ID")

        logging.info(f"Создание инструкции для ATA с: {associated_token_address}")
        
        # Define the keys in the correct order according to the ATA program
        keys = [
            # 1. Payer account
            AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
            # The payer needs:
            # - is_signer=True because they're authorizing the payment
            # - is_writable=True because they'll pay the fees

            # 2. New ATA account
            AccountMeta(pubkey=associated_token_address, is_signer=False, is_writable=True),
            # The new account needs:
            # - is_signer=False because it's a PDA
            # - is_writable=True because it's being created

            # 3. Owner's wallet
            AccountMeta(pubkey=owner, is_signer=False, is_writable=False),
            # The owner needs:
            # - is_signer=False because they don't need to sign (payer signs)
            # - is_writable=False because their account isn't modified

            # 4. Token mint
            AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
            # The mint needs:
            # - is_signer=False because it's just referenced
            # - is_writable=False because it's not modified

            # 5. System Program
            AccountMeta(pubkey=self.system_program_id, is_signer=False, is_writable=False),
            # Required to create the new account

            # 6. Token Program
            AccountMeta(pubkey=self.token_program_id, is_signer=False, is_writable=False),
            # Required to initialize the token account

            # 7. Rent Sysvar
            AccountMeta(pubkey=self.sysvar_rent_pubkey, is_signer=False, is_writable=False),
            # Required to check rent exemption
        ]
        
        # The instruction data should be empty for ATA creation
        return Instruction(
            program_id=self.associated_token_program_id,
            accounts=keys,
            data=bytes([]) # Changed: Remove instruction discriminator, ATA program doesn't need it
        )

    def create_wrap_sol_instructions(
            self,
            amount: float
        ) -> Tuple[list[Instruction], Pubkey]:
            """Create instructions to wrap SOL"""
            amount_lamports = int(amount * 10**9)
            wsol_mint = Pubkey.from_string(self.WSOL_MINT)
            
            # Get wrapped SOL token account
            wrapped_sol_account = self.find_associated_token_address(
                self.wallet.pubkey(),
                wsol_mint
            )
            
            instructions = []
            
            # Create token account if it doesn't exist
            if not self.get_token_account_info(wrapped_sol_account):
                create_account_ix = self.create_associated_token_account_ix(
                    self.wallet.pubkey(),
                    self.wallet.pubkey(),
                    wsol_mint
                )
                instructions.append(create_account_ix)
            
            # Transfer SOL to wrap
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=self.wallet.pubkey(),
                    to_pubkey=wrapped_sol_account,
                    lamports=amount_lamports
                )
            )
            instructions.append(transfer_ix)
            
            # Sync wrapped SOL balance
            sync_native_ix = Instruction(
                program_id=self.token_program_id,
                accounts=[
                    AccountMeta(pubkey=wrapped_sol_account, is_signer=False, is_writable=True)
                ],
                data=bytes([17])  # SyncNative instruction discriminator
            )
            instructions.append(sync_native_ix)
            
            return instructions, wrapped_sol_account

    def decode_pool_info(self, data: bytes) -> dict:
        """
        Decode Raydium pool data to extract token information
        
        Args:
            data: Raw pool data bytes
            
        Returns:
            dict: Decoded pool information including token addresses
        """
        try:
            if not isinstance(data, bytes):
                raise ValueError(f"Expected bytes, got {type(data)}")
                
            # Ensure minimum data length
            if len(data) < 168:  # Minimum length for required fields
                raise ValueError(f"Pool data too short: {len(data)} bytes")

            POOL_LAYOUT = {
                'status': 0,  # 1 byte
                'nonce': 1,   # 1 byte
                'token_a_mint': 8,  # 32 bytes
                'token_b_mint': 40, # 32 bytes
                'fee_account': 72,  # 32 bytes
                'token_a_vault': 104,  # 32 bytes
                'token_b_vault': 136,  # 32 bytes
            }
            
            def get_pubkey_at(offset: int) -> str:
                pubkey_bytes = data[offset:offset + 32]
                if len(pubkey_bytes) != 32:
                    raise ValueError(f"Invalid pubkey length at offset {offset}: {len(pubkey_bytes)}")
                return str(Pubkey(pubkey_bytes))
            
            pool_info = {
                'status': data[POOL_LAYOUT['status']],
                'nonce': data[POOL_LAYOUT['nonce']],
                'token_a_mint': get_pubkey_at(POOL_LAYOUT['token_a_mint']),
                'token_b_mint': get_pubkey_at(POOL_LAYOUT['token_b_mint']),
                'fee_account': get_pubkey_at(POOL_LAYOUT['fee_account']),
                'token_a_vault': get_pubkey_at(POOL_LAYOUT['token_a_vault']),
                'token_b_vault': get_pubkey_at(POOL_LAYOUT['token_b_vault']),
            }
            
            logging.info(f"Successfully decoded pool info: {pool_info}")
            return pool_info
            
        except Exception as e:
            logging.error(f"Error decoding pool info: {str(e)}")
            raise ValueError(f"Failed to decode pool info: {str(e)}")

    def get_pool_info(self, pool_address: str) -> dict:
        """
        Fetch and validate pool information from Raydium
        
        Args:
            pool_address: The address of the Raydium pool
            
        Returns:
            dict: Pool information including liquidity, fees, and token data
            
        Raises:
            ValueError: If pool info cannot be retrieved or is invalid
        """
        try:
            # Convert string address to Pubkey
            pool_pubkey = Pubkey.from_string(pool_address)
            
            # Get account info with specific commitment
            account_info = self.client.get_account_info(
                pool_pubkey,
                commitment=Confirmed,
                encoding='base64'
            )
            
            if not account_info.value:
                raise ValueError(f"Pool {pool_address} not found")
                
            # Handle the account data properly
            if hasattr(account_info.value, 'data'):
                # Check if data is a list and get the first element if it is
                data = account_info.value.data[0] if isinstance(account_info.value.data, list) else account_info.value.data
                
                # Ensure we have a string for base64 decoding
                if isinstance(data, str):
                    pool_data = base64.b64decode(data)
                elif isinstance(data, bytes):
                    pool_data = data
                elif isinstance(data, int):
                    # Convert int to bytes if necessary
                    pool_data = data.to_bytes((data.bit_length() + 7) // 8, byteorder='little')
                else:
                    raise ValueError(f"Unexpected data type: {type(data)}")
            else:
                raise ValueError("Account info does not contain data field")
            
            # Decode pool information
            pool_info = self.decode_pool_info(pool_data)
            
            logging.info(f"Successfully fetched and decoded pool info for {pool_address}")
            return pool_info
            
        except Exception as e:
            logging.error(f"Failed to fetch pool info: {str(e)}")
            raise ValueError(f"Failed to fetch pool info: {str(e)}")

    def create_swap_instruction(
        self,
        pool_address: str,
        amount_in: float,
        min_amount_out: float
    ) -> list[Instruction]:
        """Create swap instructions including ATA creation if needed"""
        pool_pubkey = Pubkey.from_string(pool_address)
        amount_in_lamports = int(amount_in * 10**9)
        min_amount_out_lamports = int(min_amount_out * 10**9)
        
        # Get pool info and extract token mints
        pool_info = self.get_pool_info(pool_address)
        token_mint_a = Pubkey.from_string(pool_info['token_a_mint'])
        token_mint_b = Pubkey.from_string(pool_info['token_b_mint'])
        
        # Get or create associated token accounts
        token_account_a = self.find_associated_token_address(self.wallet.pubkey(), token_mint_a)
        token_account_b = self.find_associated_token_address(self.wallet.pubkey(), token_mint_b)
        
        instructions = []
        
        # Check if token accounts exist and create if needed
        if not self.get_token_account_info(token_account_a):
            instructions.append(
                self.create_associated_token_account_ix(
                    self.wallet.pubkey(),
                    self.wallet.pubkey(),
                    token_mint_a
                )
            )
        
        if not self.get_token_account_info(token_account_b):
            instructions.append(
                self.create_associated_token_account_ix(
                    self.wallet.pubkey(),
                    self.wallet.pubkey(),
                    token_mint_b
                )
            )
        
        # Add transfer instruction for SOL
        if pool_info['token_a_mint'] == self.WSOL_MINT:
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=self.wallet.pubkey(),
                    to_pubkey=pool_pubkey,
                    lamports=amount_in_lamports
                )
            )
            instructions.append(transfer_ix)
        
        # Create swap instruction
        instruction_data = struct.pack(
            "<BQQ",
            9,  # Swap instruction code
            amount_in_lamports,
            min_amount_out_lamports
        )

        swap_accounts = [
            AccountMeta(pubkey=pool_pubkey, is_signer=False, is_writable=True),
            AccountMeta(pubkey=self.wallet.pubkey(), is_signer=True, is_writable=True),
            AccountMeta(pubkey=token_account_a, is_signer=False, is_writable=True),
            AccountMeta(pubkey=token_account_b, is_signer=False, is_writable=True),
            AccountMeta(pubkey=self.token_program_id, is_signer=False, is_writable=False),
            AccountMeta(pubkey=self.system_program_id, is_signer=False, is_writable=False),
            AccountMeta(pubkey=self.associated_token_program_id, is_signer=False, is_writable=False),
            # Pool specific accounts
            AccountMeta(pubkey=Pubkey.from_string(pool_info['token_a_vault']), is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(pool_info['token_b_vault']), is_signer=False, is_writable=True),
            AccountMeta(pubkey=Pubkey.from_string(pool_info['fee_account']), is_signer=False, is_writable=True)
        ]

        swap_ix = Instruction(
            program_id=self.program_id,
            accounts=swap_accounts,
            data=instruction_data
        )
        instructions.append(swap_ix)

        return instructions
    
    def make_request_with_retries(self, request_func, max_retries=5, initial_wait=2):
        """Enhanced request retry logic with RPC endpoint rotation"""
        retries = 0
        while retries < max_retries:
            try:
                return request_func()
            except (HTTPStatusError, SolanaRpcException) as e:
                if isinstance(e, HTTPStatusError) and e.response.status_code == 429:
                    # Add jitter to prevent thundering herd
                    jitter = random.uniform(0, 1)
                    wait_time = (initial_wait * (2 ** retries)) + jitter
                    
                    if retries < max_retries - 1:
                        self._rotate_rpc_endpoint()
                        cprint(f"Rate limit hit. Switched RPC endpoint and retrying in {wait_time:.2f} seconds...", 
                              "yellow", "on_red")
                    time.sleep(wait_time)
                    retries += 1
                else:
                    raise
        raise Exception(colored("Max retries exceeded for all RPC endpoints.", "red", attrs=["bold"]))
    
    def confirm_transaction_with_timeout(self, signature: str, max_timeout: int = 180) -> bool:
        """Enhanced transaction confirmation with better error handling and status checking"""
        start_time = time.time()
        confirmation_check_interval = 1.0
        error_count = 0
        max_errors = 3
        
        def get_tx_status():
            try:
                resp = self._execute_with_retry(
                    lambda: self.client.get_signature_statuses([signature])
                )
                
                if resp and resp.value and resp.value[0]:
                    return resp.value[0].confirmation_status
                return None
            except Exception as e:
                logging.warning(f"Error checking transaction status: {str(e)}")
                return None

        while time.time() - start_time < max_timeout:
            try:
                status = get_tx_status()
                
                if status == "finalized":
                    # Double check transaction success
                    tx_info = self._execute_with_retry(
                        lambda: self.client.get_transaction(
                            signature,
                            commitment=Finalized,
                            max_supported_transaction_version=0
                        )
                    )
                    
                    if tx_info and tx_info.value:
                        if hasattr(tx_info.value, 'meta') and tx_info.value.meta:
                            if tx_info.value.meta.err:
                                logging.error(f"Transaction failed: {tx_info.value.meta.err}")
                                return False
                            logging.info("Transaction successfully finalized")
                            return True
                
                elif status == "confirmed":
                    logging.info("Transaction confirmed, waiting for finalization...")
                elif status == "processed":
                    logging.info("Transaction processed, waiting for confirmation...")
                elif status is None:
                    error_count += 1
                    if error_count >= max_errors:
                        logging.error("Too many errors checking transaction status")
                        self._rotate_rpc_endpoint()
                        error_count = 0
                
                # Adaptive sleep with upper bound
                sleep_time = min(confirmation_check_interval * 1.5, 10)
                time.sleep(sleep_time)
                confirmation_check_interval = sleep_time
                
            except Exception as e:
                error_count += 1
                logging.warning(f"Error in confirmation loop: {str(e)}")
                
                if error_count >= max_errors:
                    self._rotate_rpc_endpoint()
                    error_count = 0
                
                time.sleep(2)

        logging.error(f"Transaction confirmation timed out after {max_timeout} seconds")
        return False
    def swap(
        self,
        pool_address: str,
        amount_in: float = 0.001,
        slippage: float = 0.06
    ) -> Optional[str]:
        """Execute swap with improved error handling and RPC fallback"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Wrap all RPC calls with retry logic
                pool_info = self._execute_with_retry(
                    lambda: self.get_pool_info(pool_address)
                )
                
                instructions = []
                if pool_info['token_a_mint'] == self.WSOL_MINT:
                    wrap_instructions, wrapped_sol_account = self.create_wrap_sol_instructions(amount_in)
                    instructions.extend(wrap_instructions)

                min_amount_out = amount_in * (1 - slippage)
                swap_ix = self.create_swap_instruction(pool_address, amount_in, min_amount_out)
                instructions.extend(swap_ix)

                # Get recent blockhash with retry
                recent_blockhash = self._execute_with_retry(
                    lambda: self.client.get_latest_blockhash(commitment=Finalized).value.blockhash
                )

                # Create and sign transaction
                message = Message.new_with_blockhash(
                    instructions=instructions,
                    payer=self.wallet.pubkey(),
                    blockhash=recent_blockhash
                )

                transaction = Transaction(
                    from_keypairs=[self.wallet],
                    message=message,
                    recent_blockhash=recent_blockhash
                )

                # Send transaction with enhanced options
                signature = self._execute_with_retry(
                    lambda: self.client.send_transaction(
                        transaction,
                        opts=TxOpts(
                            skip_preflight=True,
                            max_retries=5,
                            preflight_commitment=Confirmed
                        )
                    ).value
                )

                logging.info(f"Transaction sent: {signature}")
                cprint(f"Transaction sent: {signature}", "white", "on_green")
                
                 # Confirm transaction with enhanced timeout handling
                if self.confirm_transaction_with_timeout(signature, max_timeout=240):
                    return signature
                
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count + random.uniform(0, 1)
                    logging.info(f"Transaction failed, retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    self._rotate_rpc_endpoint()
                else:
                    raise Exception("Transaction confirmation timeout")

            except Exception as e:
                retry_count += 1
                logging.error(f"Swap attempt {retry_count} failed: {str(e)}")
                
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count + random.uniform(0, 1)
                    cprint(f"Retrying swap in {wait_time:.2f} seconds...", "yellow")
                    time.sleep(wait_time)
                    self._rotate_rpc_endpoint()
                else:
                    logging.error("Max retry attempts reached")
                    raise Exception(f"Swap failed after {max_retries} attempts: {str(e)}")

        return None

if __name__ == "__main__":
    try:
        PRIVATE_KEY = os.getenv("PRIVATE_KEY")
        if not PRIVATE_KEY:
            raise ValueError("PRIVATE_KEY environment variable not set")
            
        POOL_ADDRESS = "9kexJ56K94TKZrMXcwaMk43GpAFkpvGGjQGQj3eeKwVX"
        
        swap_client = RaydiumSwap(PRIVATE_KEY)
        
        result = swap_client.swap(
            pool_address=POOL_ADDRESS,
            amount_in=0.002,
            slippage=0.06
        )
        
        if result:
            cprint(f"Swap successful! Transaction signature: {result}", "yellow", "on_light_green")
            cprint(f"View transaction: https://solscan.io/tx/{result}", "green", "on_light_magenta")
            
    except Exception as e:
        logging.error(f"Swap failed: {str(e)}")
        cprint(f"Swap failed: {str(e)}", "white", "on_red")
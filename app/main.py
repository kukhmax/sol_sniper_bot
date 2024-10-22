import os
from typing import Optional
from solana.rpc.api import Client
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey  # type: ignore
from solana.transaction import Transaction
from solders.instruction import Instruction, AccountMeta  # type: ignore
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.system_program import ID as SYS_PROGRAM_ID
from spl.token.constants import TOKEN_PROGRAM_ID
import base58
from termcolor import colored
import struct

# Константы
RAYDIUM_PROGRAM_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
AMOUNT = 0.001  # Сумма свопа в SOL
SLIPPAGE = 0.5  # Проскальзывание 0.5%

# Конфигурация пула и токенов
POOL_CONFIG = {
    "amm_id": Pubkey.from_string("FAfxE77HNQYsNN3a2eyKhXe3mYpRQUS7tyXWMCzDBNQC"),
    "token_a": Pubkey.from_string("So11111111111111111111111111111111111111112"),  # SOL
    "token_b": Pubkey.from_string("CauybpUD3sjHVC5UEUXVCwxpMTXnrgn3AEF9bE3xpump"),  # Токен B
    "pool_authority": Pubkey.from_string("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1"),
    "open_orders": Pubkey.from_string("J8u8nTHYtvudyqwLrXZboziN95LpaHFHpd97Jm5vtbkW"),
    "target_orders": Pubkey.from_string("3cji8XW5uhtsA757vELVFAeJpskyHwbnTSceMFY5GjV3"),
    "vault_a": Pubkey.from_string("FAfxE77HNQYsNN3a2eyKhXe3mYpRQUS7tyXWMCzDBNQC"),
    "vault_b": Pubkey.from_string("FAfxE77HNQYsNN3a2eyKhXe3mYpRQUS7tyXWMCzDBNQC"),
}

class RaydiumSwap:
    def __init__(self):
        self.client = Client("https://api.mainnet-beta.solana.com", commitment=Confirmed)
        private_key = os.getenv("PRIVATE_KEY")
        if not private_key:
            raise ValueError("Не установлен PRIVATE_KEY в переменных окружения")
        self.keypair = Keypair.from_bytes(base58.b58decode(private_key))

    def create_swap_instruction(self, amount_in: int, minimum_amount_out: int) -> Instruction:
        """
        Создает инструкцию для свопа на Raydium
        """
        # Формат данных для инструкции свопа
        # [u8(2), u64(amount_in), u64(minimum_amount_out)]
        data = struct.pack("<BQQ", 2, amount_in, minimum_amount_out)

        accounts = [
            # Обязательные аккаунты для свопа
            AccountMeta(pubkey=self.keypair.pubkey(), is_signer=True, is_writable=True),
            AccountMeta(pubkey=POOL_CONFIG["amm_id"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=POOL_CONFIG["pool_authority"], is_signer=False, is_writable=False),
            AccountMeta(pubkey=POOL_CONFIG["open_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=POOL_CONFIG["target_orders"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=POOL_CONFIG["vault_a"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=POOL_CONFIG["vault_b"], is_signer=False, is_writable=True),
            AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
            AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
        ]

        return Instruction(
            program_id=RAYDIUM_PROGRAM_ID,
            data=data,
            accounts=accounts
        )

    def swap(self, amount_in: float) -> Optional[str]:
        """
        Выполняет своп токенов через Raydium
        """
        # try:
        # Конвертируем amount_in в ламports (1 SOL = 10^9 ламports)
        amount_in_lamports = int(amount_in * 10**9)
        
        # Рассчитываем минимальное количество получаемых токенов с учетом проскальзывания
        minimum_amount_out = int(amount_in_lamports * (1 - SLIPPAGE / 100))

        # Получаем последний блокхеш
        recent_blockhash = self.client.get_latest_blockhash()
        
        # Создаем транзакцию
        transaction = Transaction()
        transaction.recent_blockhash = recent_blockhash.value.blockhash
        
        # Добавляем инструкцию свопа
        swap_ix = self.create_swap_instruction(amount_in_lamports, minimum_amount_out)
        transaction.add(swap_ix)

        # Добавляем fee payer
        transaction.fee_payer = self.keypair.pubkey()
        
        # Подписываем транзакцию
        transaction.sign(self.keypair)

        # Корректно формируем опции для отправки транзакции
        # Создаем опции через TxOpts
        opts = TxOpts(
            skip_preflight=True,
            # encoding="base64",
            max_retries=3,
        )

         # Получаем сериализованную транзакцию в правильном формате
        serialized_transaction = transaction.serialize().hex()
        print(colored(f"Транзакция {serialized_transaction}", "yellow"))
    
        # Отправляем транзакцию, используя raw_transaction
        result = self.client.send_raw_transaction(
            transaction.serialize(),
            opts=opts
        )

        signature = result.value
        print(colored(f"Транзакция отправлена: {signature}", "green"))
        
        # Ждем подтверждения транзакции
        confirmation = self.client.confirm_transaction(signature)
        if confirmation.value.err:
            raise Exception("Ошибка при подтверждении транзакции")
            
        return signature

        # except Exception as e:
        #     print(colored(f"Ошибка при свопе: {str(e)}", "red"))
        #     return None

def main():
    # try:
        swapper = RaydiumSwap()
        signature = swapper.swap(AMOUNT)
        if signature:
            print(colored(f"Своп успешно выполнен! Signature: {signature}", "green"))
    # except Exception as e:
    #     print(colored(f"Ошибка в основном цикле: {str(e)}", "red"))

if __name__ == "__main__":
    main()
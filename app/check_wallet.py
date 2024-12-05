import solders
import solana
import pandas as pd
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solders.pubkey import Pubkey  # type: ignore
import asyncio
import json
from datetime import datetime
from termcolor import colored, cprint

class SolanaTransactionFetcher:
    def __init__(self, rpc_url, wallet_pubkey, limit=100):
        """
        Инициализация класса для извлечения транзакций
        
        :param rpc_url: URL RPC-сервера Solana
        :param wallet_pubkey: Публичный ключ кошелька в виде строки
        :param limit: Максимальное количество транзакций для извлечения
        """
        self.rpc_url = rpc_url
        self.wallet_pubkey = Pubkey.from_string(wallet_pubkey)
        self.limit = limit
        self.client = AsyncClient(self.rpc_url)

    async def fetch_transactions(self):
        """
        Асинхронное извлечение signature транзакций для указанного кошелька
        
        :return: Список signature транзакций
        """
        try:
            signatures_response = await self.client.get_signatures_for_address(
                self.wallet_pubkey,
                limit=self.limit,
                commitment=Confirmed
            )
            
            signatures = [tx.signature for tx in signatures_response.value]
            # print(signatures)
            return signatures
        
        except Exception as e:
            print(f"Ошибка при извлечении транзакций: {e}")
            return []

    async def get_transaction_details(self, signatures):
        """
        Получение деталей транзакций по их signature
        
        :param signatures: Список signature транзакций
        :return: DataFrame с деталями транзакций
        """
        transaction_details = []
        for signature in signatures:
            try:
                await asyncio.sleep(5)
                # Получаем полную информацию о транзакции
                tx_response = await self.client.get_transaction(
                    signature, 
                    commitment=Confirmed,
                    encoding="jsonParsed",
                    max_supported_transaction_version=0
                )

                account_keys = [str(key) for key in tx_response.value.transaction.transaction.message.account_keys]
                if "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1" in account_keys:
                    trans = tx_response.value.transaction

                    instructions = trans.transaction.message

                    cprint(f"Print instructions RAW:\n{instructions.instructions}", "yellow")

                    # # фильтруем по program_id (в данном случае - RaydiumLPV4)
                    # filtered_instructions = [
                    #     instruction for instruction in instructions if instruction.program_id == Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
                    # ]
                    # cprint(f"Print filtered instructions RAW:\n{filtered_instructions}", "yellow")


                    pre_balance = trans.meta.pre_token_balances
                    post_balance = trans.meta.post_token_balances
                    
                    # sol = self.from_token if self.from_token == "So11111111111111111111111111111111111111112" else self.to_token
                    # new_token = self.from_token if self.from_token != "So11111111111111111111111111111111111111112" else self.to_token

                    # diffs = {sol: 0, new_token: 0}
                    # try:
                    #     for pre in pre_balance:                    
                    #         for post in post_balance:                       
                    #             if pre.account_index == post.account_index:                            

                    #                 pre_ui_amount = float(pre.ui_token_amount.ui_amount_string)
                    #                 post_ui_amount = float(post.ui_token_amount.ui_amount_string)
                    #                 decimal = post.ui_token_amount.decimals             
                    #                 diff = round(post_ui_amount - pre_ui_amount, decimal)
                    #                 pre_mint = str(pre.mint)
                    #                 post_mint = str(post.mint)
                                    
                                    
                    #                 if abs(diff) > 0:
                    #                     # print(colored(f"Account index: {pre.account_index} <> {post.account_index}", "light_yellow", attrs=["bold", "reverse"]), 
                    #                     # colored(pre_mint, "white", "on_black"), colored(post_mint, "white", "on_black"), 
                    #                     # colored(f" amount: {pre_ui_amount} - {post_ui_amount} = {diff}", "cyan"))
                                                        
                    #                     if pre_mint == sol:
                    #                         diffs[sol] = abs(diff)
                    #                     elif pre_mint == new_token:
                    #                         diffs[new_token] = abs(diff)
                    # except Exception as e:
                    #     cprint(f"Error while getting diffs: {str(e)}", "red", attrs=["bold", "reverse"])

                    # # print()
                    # # cprint(diffs, "magenta", attrs=["bold"])
                    # bought_tokens_amount = diffs[new_token]
                    # cprint(f"Amount of new token: {bought_tokens_amount:.8f} tokens ", "magenta", attrs=["bold"])
                    
                    # print()
                    # try:     
                    #     price = diffs[sol] / diffs[new_token]
                    # except ZeroDivisionError:
                    #     price = 0
                    
                    # print(colored(f"Current price: ", "magenta"), colored(f"{price:.14f} ", "yellow", attrs=["bold"]),
                    #     colored(f"  Time: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}", "cyan", attrs=["bold"]))

                    # print(trans.transaction.signatures[0])
                    # print(trans)
                    # print()

                
                # Извлекаем базовую информацию безопасно
                    tx_details = {
                        'signature': signature,
                        'raw_transaction': json.dumps(trans.meta.to_json())
                    }
                    
                    transaction_details.append(tx_details)
            
            except Exception as e:
                print(f"Ошибка при получении деталей транзакции {signature}: {e}")
                print()
                # Логируем полную информацию об ошибке для отладки
                # import traceback
                # traceback.print_exc()
        
        return pd.DataFrame(transaction_details)

    async def save_to_csv(self, dataframe, filename='solana_transactions.csv'):
        """
        Сохранение DataFrame в CSV-файл
        
        :param dataframe: DataFrame с транзакциями
        :param filename: Имя файла для сохранения
        """
        try:
            dataframe.to_csv(filename, index=False, encoding='utf-8')
            print(f"Транзакции сохранены в {filename}")
        except Exception as e:
            print(f"Ошибка при сохранении в CSV: {e}")

    async def run(self):
        """
        Основной метод для выполнения всего процесса
        """
        signatures = await self.fetch_transactions()
        if signatures:
            print(f"Найдено транзакций: {len(signatures)}")
            transactions_df = await self.get_transaction_details(signatures)
            await self.save_to_csv(transactions_df)
        else:
            print("Не удалось извлечь signature транзакций")

async def main():
    # Пример использования
    RPC_URL = "https://api.mainnet-beta.solana.com"  # Основной RPC-сервер Solana
    WALLET_PUBKEY = "7HRoS2UuKTjb2pzzAt9trYedarjWQGkiKedffctLNFx4"  # Замените на ваш реальный публичный ключ
    TRANSACTION_LIMIT = 20  # Количество транзакций для извлечения

    fetcher = SolanaTransactionFetcher(RPC_URL, WALLET_PUBKEY, TRANSACTION_LIMIT)
    await fetcher.run()

if __name__ == "__main__":
    asyncio.run(main())
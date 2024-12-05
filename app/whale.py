import asyncio
import json
import websockets
from datetime import datetime
import pandas as pd
from solana.rpc.websocket_api import connect
from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.rpc.responses import SubscriptionResult

class SolanaMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Pubkey.from_string(wallet_address)
        self.client = AsyncClient("https://api.mainnet-beta.solana.com", commitment="confirmed")
        self.transactions_data = []
        self.ws_url = "wss://api.mainnet-beta.solana.com"
        self.subscription_id = None
        self.last_ping_time = None
        self.ping_interval = 20
        
        self.raydium_programs = [
            "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "27haf8L6oxUeXrHrgEgsexjSY5hbVUWEmvv9Nyxg8vQv",
            "CAMMCzo5YL8w4VFF8KKwtV5yVBrXdZQ5RJWkX6t1nmQ3"
        ]

    async def process_transaction(self, signature: str):
        try:
            tx = await self.client.get_transaction(
                Signature.from_string(signature),
                max_supported_transaction_version=0
            )
            
            if tx and tx_data.transaction.meta.pre_token_balances:
                tx_data = tx.value
                print(tx_data)
                
                # Получаем список account keys из транзакции
                account_keys = []
                if hasattr(tx_data.transaction, 'message'):
                    # Для legacy транзакций
                    message = tx_data.transaction.message
                    print(message)
                    if hasattr(message, 'account_keys'):
                        account_keys = [str(key) for key in message.account_keys]
                elif hasattr(tx_data.transaction, 'account_keys'):
                    # Прямой доступ к account_keys
                    account_keys = [str(key) for key in tx_data.transaction.account_keys]
                else:
                    # Попытка получить из decoded_message
                    try:
                        decoded = tx_data.transaction.decoded
                        if decoded and hasattr(decoded, 'account_keys'):
                            account_keys = [str(key) for key in decoded.account_keys]
                            print(account_keys)
                    except:
                        pass
                
                # Проверяем, является ли транзакция Raydium транзакцией
                is_raydium = any(prog_id in account_keys for prog_id in self.raydium_programs)
                
                if is_raydium:
                    transaction_info = {
                        'timestamp': datetime.fromtimestamp(tx_data.block_time).strftime('%Y-%m-%d %H:%M:%S') if tx_data.block_time else 'Unknown',
                        'signature': signature,
                        'slot': tx_data.slot,
                        'success': tx_data.meta.status.Ok is not None if hasattr(tx_data.meta.status, 'Ok') else False,
                        'fee': tx_data.meta.fee if hasattr(tx_data.meta, 'fee') else 0,
                    }
                    
                    self.transactions_data.append(transaction_info)
                    self.save_to_csv()
                    
                    print(f"Новая Raydium транзакция: {signature}")
                    print(json.dumps(transaction_info, indent=2))

        except Exception as e:
            print(f"Ошибка при обработке транзакции {signature}: {str(e)}")

    def save_to_csv(self):
        if self.transactions_data:
            df = pd.DataFrame(self.transactions_data)
            df.to_csv('raydium_transactions.csv', index=False)

    async def keep_alive(self, websocket):
        while True:
            try:
                await websocket.ping()
                await asyncio.sleep(self.ping_interval)
            except Exception as e:
                print(f"Ошибка в keep_alive: {str(e)}")
                break

    async def subscribe(self, websocket):
        try:
            subscribe_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "accountSubscribe",
                "params": [
                    str(self.wallet),
                    {"encoding": "jsonParsed", "commitment": "confirmed"}
                ]
            }
            await websocket.send(json.dumps(subscribe_message))
            response = await websocket.recv()
            response_data = json.loads(response)
            if 'result' in response_data:
                self.subscription_id = response_data['result']
                print(f"Успешная подписка, ID: {self.subscription_id}")
            return True
        except Exception as e:
            print(f"Ошибка при подписке: {str(e)}")
            return False

    async def monitor_transactions(self):
        while True:
            try:
                async with websockets.connect(self.ws_url) as websocket:
                    print(f"Начат мониторинг кошелька: {self.wallet}")
                    
                    if not await self.subscribe(websocket):
                        continue

                    keep_alive_task = asyncio.create_task(self.keep_alive(websocket))

                    try:
                        while True:
                            try:
                                message = await websocket.recv()
                                message_data = json.loads(message)
                                print(message_data)
                                
                                if 'params' in message_data:
                                    try:
                                        signatures = await self.client.get_signatures_for_address(self.wallet, limit=5)
                                        if signatures and signatures.value:
                                            for sig_info in signatures.value:
                                                await self.process_transaction(str(sig_info.signature))
                                    except Exception as e:
                                        print(f"Ошибка при получении транзакций: {str(e)}")

                            except json.JSONDecodeError as e:
                                print(f"Ошибка декодирования JSON: {str(e)}")
                                continue

                    except websockets.exceptions.ConnectionClosed:
                        print("Соединение закрыто, переподключение...")
                    finally:
                        keep_alive_task.cancel()
                        try:
                            await keep_alive_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                print(f"Ошибка соединения: {str(e)}")
                print("Переподключение через 5 секунд...")
                await asyncio.sleep(5)

async def main():


    wallet_address = "7HRoS2UuKTjb2pzzAt9trYedarjWQGkiKedffctLNFx4"
    
    monitor = SolanaMonitor(wallet_address)
    print("Запуск мониторинга...")
    # await monitor.process_transaction('4ckX2mu1t7V3cBYFU6EiWbKwuP1PewohefSJkKxFzSwUfEYEiJY3FaWdMafSsqLBWVoaDiM6AEQSU9ECoo2iYJPT')
    
    while True:
        try:
            await monitor.monitor_transactions()
        except Exception as e:
            print(f"Критическая ошибка: {str(e)}")
            print("Перезапуск через 5 секунд...")
            await asyncio.sleep(5)
        finally:
            try:
                await monitor.client.close()
            except:
                pass

if __name__ == "__main__":
    asyncio.run(main())

# Ошибка при обработке транзакции SGNWn6Uutcux1qF15JUsvWYNRNAgsptFWbjSqwmQcjwdCwdjEpNW8rCkJ4v6djsjnQ3WDz5vpa4coLxbgTq5MCL: list index out of range
# Ошибка при обработке транзакции 6pnRTCEzu9WCGHbv4hyV2JhGYns9VuvpcPuXcJcyiB8VJfySSDzAFqT8aYBidrdue4ysuZbTM4LTzT25Jou6pZX: list index out of range
# Ошибка при обработке транзакции 5UygCmbRBELoTmcwU8fdiug3Mm8tKyU3ADr1UCLwBAfj6pAGrhPfKu6GgxXaBheDiQhBZM28pVSKteRSq8r5JAGR: 
# Ошибка при обработке транзакции cRq7AbY51ak2LmZ4DQL1GUVENa89XzRUMU9yv66HCShoGYAvxU9KfsvnwhP5GinQy9zzEdSbGHo2RCWkeKdRy63: 
# Ошибка при обработке транзакции 4ckX2mu1t7V3cBYFU6EiWbKwuP1PewohefSJkKxFzSwUfEYEiJY3FaWdMafSsqLBWVoaDiM6AEQSU9ECoo2iYJPT: 
import asyncio
import logging
import time
from solana.rpc.websocket_api import connect as ws_connect
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey
from utils import (
    initialize_configurations, 
    setup_snipe_list_monitoring, 
    log_error_to_file, 
    get_pool_keys_from_market_id, 
    sleep
)

# Конфигурации и константы
BUY_DELAY = 0.5
TOKEN_SYMBOL_FILTER = "mytoken"
logger = logging.getLogger(__name__)

# Массив для хранения сигнатур
seen_signatures = set()
pending_snipe_list = []
token_symbol_to_snipe = TOKEN_SYMBOL_FILTER.lower()

# Инициализация и подключение к WebSocket
async def monitor_new_tokens():
    try:
        # Инициализация конфигураций
        await initialize_configurations()

        # Настройка мониторинга списка снайпинга
        setup_snipe_list_monitoring(pending_snipe_list, logger)

        logger.info("Monitoring new Solana tokens...")

        # RPC WebSocket клиент для подписки на транзакции
        async with ws_connect("ws://api.mainnet-beta.solana.com") as websocket:
            async for message in websocket:
                logs = message.get('value', {}).get('logs', [])
                err = message.get('value', {}).get('err', None)
                signature = message.get('value', {}).get('signature', "")

                # Пропускаем, если есть ошибка или сигнатура уже видена
                if err or signature in seen_signatures:
                    continue

                logger.info(f"Found new token signature: {signature}")
                seen_signatures.add(signature)

                # Получаем информацию о пуле ликвидности
                pool_keys = await get_pool_keys_from_market_id(logs)

                # Проверяем, есть ли токен в списке для снайпинга
                if pool_keys.base_mint.to_base58() in pending_snipe_list:
                    current_time = int(time.time())
                    delay_ms = (pool_keys.pool_open_time - current_time) * 1000
                    
                    if delay_ms > 0:
                        logger.info(f"Pool open in future for {pool_keys.base_mint}. Waiting {delay_ms / 1000} seconds.")
                        await sleep(delay_ms / 1000)

                    logger.info(f"Pool open delay complete for {pool_keys.base_mint}. Executing buy...")
                    # Здесь будет логика покупки токена

    except Exception as e:
        log_error_to_file(e)

if __name__ == '__main__':
    asyncio.run(monitor_new_tokens())

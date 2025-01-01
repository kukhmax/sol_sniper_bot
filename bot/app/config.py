import logging.handlers
import os
import base58
import logging
from solana.rpc.api import Client
from solders.keypair import Keypair  # type: ignore
import dotenv
from colorama import Fore, Style, init

dotenv.load_dotenv()

SECRET_KEY = os.getenv("PRIVATE_KEY")
RPC = "https://mainnet.helius-rpc.com/?api-key=8c91081f-d02b-472f-9f4b-fea3c9b7195c"  # ignore E501
MAIN_RPC = "https://api.mainnet-beta.solana.com"
UNIT_BUDGET = 100_000
UNIT_PRICE = 1_000_000
client = Client(RPC)
# payer_keypair = Keypair.from_base58_string(PRIV_KEY)
payer_keypair = Keypair.from_bytes(base58.b58decode(SECRET_KEY))

payer_pubkey = payer_keypair.pubkey()

init()

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': Fore.BLUE,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        record.levelname = f'{color}{record.levelname}{Style.RESET_ALL}'
        return super().format(record)

 
class SensitiveDataFilter(logging.Filter):
    def filter(self, record):
        # Return False if the log message contains sensitive API endpoints or keys
        sensitive_patterns = [
            "helius-rpc.com/?api-key=",
            "HTTP Request: POST https://mainnet",
            "HTTP Response: 200 OK",
            "Got difference for"  # .venv/lib/python3.13/site-packages/telethon/client/updates.py
        ]
        return not any(pattern in record.getMessage() for pattern in sensitive_patterns)


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create the filter
    sensitive_filter = SensitiveDataFilter()
    
    # Apply filter to root logger
    logger.addFilter(sensitive_filter)


    # Форматтеры
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(levelname)s - %(message)s - [%(funcName)s:%(lineno)d]"
    )

    # Ротируемый файловый обработчик
    file_handler = logging.handlers.RotatingFileHandler(
        '/app/logs/scrap_bot.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(sensitive_filter)  # Add filter to file handler

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(sensitive_filter)  # Add filter to console handler

    # Добавляем обработчики
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

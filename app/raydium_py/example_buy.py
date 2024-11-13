from raydium import buy
from utils import get_pair_address
import requests

# Buy Example
token_address = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr" # POPCAT
pair_address = get_pair_address(token_address)
sol_in = 0.01
slippage = 10
# buy(pair_address, sol_in, slippage)

def get_pair_address(mint):
    url = f"https://api-v3.raydium.io/pools/info/mint?mint1={mint}&poolType=all&poolSortField=default&sortType=desc&pageSize=1&page=1"
    try:
        response = requests.get(url)
        response.raise_for_status() 
        pair_address = response.json()['data']['data'][0]['id']
        return pair_address
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")
        return None


if __name__ == "__main__":
    token_address = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr" # POPCAT
    pair_address = get_pair_address(token_address)
    print(type(pair_address))

    # FRhB8L7Y9Qq41qZXYLtC2nw8An1RJfLLxRF2x9RwLLMo
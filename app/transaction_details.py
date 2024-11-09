from playwright.sync_api import sync_playwright
from termcolor import colored, cprint
import time

def extract_solana_tx_data(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # headless=False чтобы видеть процесс
        page = browser.new_page()
        
        # Переходим на страницу транзакции
        page.goto(url)
        
        # Ждем загрузки таблицы токенов
        page.wait_for_selector("tbody.list")
        try:
            cost_of_swap_with_fee = page.locator("div.table-responsive.mb-0 > table > tbody > tr:nth-child(1) > td:nth-child(3) > span > span > span").text_content()
            
        except Exception as e:
            cprint(f"Failed to find cost of swap: {e}", "red", attrs=["bold", "reverse"])
            cost_of_swap_with_fee = None
            
        # Даем время на полную загрузку данных (может потребоваться настройка)
        time.sleep(2)
        
        # Извлекаем данные используя JavaScript
        token_data = page.evaluate('''
            () => {
                const rows = document.querySelectorAll('tbody.list tr');
                return Array.from(rows).map(row => {
                    const fromAddress = row.querySelector('td:first-child .font-monospace a')?.textContent || '';
                    const tokenAddress = row.querySelector('td:nth-child(2) .font-monospace a')?.textContent || '';
                    const balanceChange = row.querySelector('td:nth-child(3) .badge')?.textContent || '';
                    const amount = row.querySelector('td:nth-child(4)')?.textContent || '';
                    
                    return {
                        from_address: fromAddress.trim(),
                        token_address: tokenAddress.trim(),
                        balance_change: balanceChange.trim(),
                        amount: amount.trim()
                    };
                });
            }
        ''')
        
        browser.close()
        return token_data, cost_of_swap_with_fee

def format_token_data(data):
    """Форматирует данные для удобного просмотра"""
    formatted = []
    for item in data:        
        formatted.append(
            f"From: {item['from_address']}\n"
            f"Token: {item['token_address']}\n"
            f"Change: {item['balance_change']}\n"
            f"Amount: {item['amount']}\n"
            f"{'-' * 50}"
            )
    return "\n".join(formatted)

def save_to_file(data, filename="solana_tx_data.txt"):
    """Сохраняет данные в файл"""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(format_token_data(data))

def get_solana_tx_data(tx):
    url = f"https://explorer.solana.com/tx/{tx}"
    try:
        cprint("Начинаем извлечение данных...", "yellow")
        data, wsol_with_fee = extract_solana_tx_data(url)
        new_data = []
        for item in data:
            if item['from_address'] and item['amount']:
                new_data.append(item)

        
        cprint("\nИзвлеченные данные:", "green", attrs=["bold"])
        cprint(format_token_data(new_data), "light_cyan")
        
        # Сохраняем в файл
        save_to_file(new_data)
        cprint(f"\nДанные сохранены в файл: solana_tx_data.txt", "magenta", attrs=["bold"])
        cprint("==========================================", "light_grey")

        for item in new_data:
            if "SOL" in item['token_address'] and float(item['balance_change']) > 0:
                wsol = abs(float(item['balance_change']))
                cprint(f"{abs(float(item['balance_change']))} WSOL", "cyan", attrs=["bold"])
            elif "pump" in item['token_address'] and float(item['balance_change']) > 0:
                new_token = abs(float(item['balance_change']))
                token = item['amount'].split(' ')[1]
                cprint(f"{item['balance_change']} {token}", "light_magenta", attrs=["bold"])
        
        price = wsol / new_token

        cprint(f"Cost of swap {token}/SOL on Raydium with fee is: {wsol_with_fee}", "green", attrs=["bold"])
        cprint(f"Price: {price:.12f}", "yellow", attrs=["bold"])

        return wsol_with_fee, wsol, new_token, price

    
        
    except Exception as e:
        cprint(f"Произошла ошибка: {str(e)}", "red", attrs=["bold", "reverse"])


if __name__ == "__main__":
    buy_tx = "jHh9ufmGu22yysk8Rgyb5Ly85A3iQB1UyPLoFchomGLsV8NQyTwMkJ2iNeLpktRrFUDz8ua6bkpehiy4Ujpnbfj"
    get_solana_tx_data(buy_tx)

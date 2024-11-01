import time
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional
from termcolor import colored, cprint

@dataclass
class FeeBreakdown:
    base_fee: float = 0.000005  # 5000 lamports
    compute_units_fee: float = 0
    dex_fee: float = 0
    rent_fee: float = 0
    network_load_multiplier: float = 1.0
    priority_fee: float = 0

    @property
    def total_fee(self) -> float:
        return (self.base_fee + 
                self.compute_units_fee + 
                self.dex_fee + 
                self.rent_fee) * self.network_load_multiplier + self.priority_fee

class FeeCalculator:
    def __init__(self):
        self.fee_history: Dict[int, FeeBreakdown] = {}
        
    async def estimate_fees(self, swap_amount: float, priority_fee: float) -> FeeBreakdown:
        fee = FeeBreakdown()
        
        # Базовая комиссия
        fee.base_fee = 0.000005
        
        # Примерный расчет Compute Units
        estimated_cu = 300000  # среднее значение для Raydium swap
        fee.compute_units_fee = (estimated_cu / 1000) * 0.000008  # примерная стоимость CU
        
        # Комиссия DEX
        fee.dex_fee = swap_amount * 0.0025  # 0.25%
        
        # Примерная комиссия за rent
        fee.rent_fee = 0.000001
        
        # Приоритетная комиссия
        fee.priority_fee = priority_fee
        
        # Получаем текущий network load multiplier
        fee.network_load_multiplier = await self.get_network_load_multiplier()
        
        return fee

    async def get_network_load_multiplier(self) -> float:
        """
        Получает множитель нагрузки сети на основе текущей загруженности
        """
        # Здесь можно добавить запрос к RPC для получения реальной загрузки сети
        # Пока используем упрощенный вариант на основе времени
        hour = time.localtime().tm_hour
        
        # В периоды высокой активности (UTC)
        if 13 <= hour <= 21:  # примерно 9:00 - 17:00 EST
            return 1.5
        return 1.0

    def log_fee(self, timestamp: int, fee: FeeBreakdown):
        self.fee_history[timestamp] = fee
        
    def print_fee_breakdown(self, fee: FeeBreakdown, swap_amount: float):
        total = fee.total_fee + swap_amount
        
        cprint("\n=== Fee Breakdown ===", "cyan", attrs=["bold"])
        cprint(f"Swap Amount: {swap_amount:.6f} SOL", "white")
        cprint(f"Base Fee: {fee.base_fee:.6f} SOL", "white")
        cprint(f"Compute Units Fee: {fee.compute_units_fee:.6f} SOL", "white")
        cprint(f"DEX Fee (0.25%): {fee.dex_fee:.6f} SOL", "white")
        cprint(f"Rent Fee: {fee.rent_fee:.6f} SOL", "white")
        cprint(f"Network Load Multiplier: {fee.network_load_multiplier}x", "yellow")
        cprint(f"Priority Fee: {fee.priority_fee:.6f} SOL", "yellow")
        cprint(f"Total Fee: {fee.total_fee:.6f} SOL", "green", attrs=["bold"])
        cprint(f"Total Transaction: {total:.6f} SOL", "red", attrs=["bold"])
        cprint("==================\n", "cyan", attrs=["bold"])

async def analyze_fees(swap_amount: float, priority_fee: float) -> None:
    calculator = FeeCalculator()
    fee_breakdown = await calculator.estimate_fees(swap_amount, priority_fee)
    calculator.print_fee_breakdown(fee_breakdown, swap_amount)
    
    return fee_breakdown


if __name__ == "__main__":
    asyncio.run(analyze_fees(0.1, 0.00005))
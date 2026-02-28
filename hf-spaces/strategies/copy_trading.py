"""
跟单交易模块
"""
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from config.settings import config
from core.client import PolymarketClient


@dataclass
class TraderInfo:
    """交易者信息"""
    address: str
    pnl: float = 0.0
    win_rate: float = 0.0
    rank: int = 0


@dataclass
class CopyTrade:
    """跟单交易记录"""
    original_trader: str
    copy_size: float
    copy_price: float
    status: str = "pending"
    timestamp: datetime = field(default_factory=datetime.now)


class CopyTradingBot:
    """跟单交易机器人"""
    
    def __init__(self, client: PolymarketClient):
        self.client = client
        
        self.copy_ratio = config.trading.COPY_TRADE_RATIO
        self.min_size = config.trading.MIN_COPY_SIZE
        self.max_size = config.trading.MAX_COPY_SIZE
        self.simulation = config.trading.SIMULATION_MODE
        
        self.target_traders: Set[str] = set()
        self.trader_info: Dict[str, TraderInfo] = {}
        self.processed_trades: Set[str] = set()
        self.copy_trades: List[CopyTrade] = []
        
        self.on_copy_trade: Optional[Callable] = None
    
    def add_trader(self, address: str, pnl: float = 0, win_rate: float = 0, rank: int = 0):
        """添加跟单目标"""
        self.target_traders.add(address)
        self.trader_info[address] = TraderInfo(
            address=address,
            pnl=pnl,
            win_rate=win_rate,
            rank=rank
        )
        logger.info(f"✅ 添加跟单目标: {address[:16]}...")
    
    def remove_trader(self, address: str):
        """移除跟单目标"""
        self.target_traders.discard(address)
        logger.info(f"❌ 移除跟单目标: {address[:16]}...")
    
    async def execute_copy(self, trader_address: str, trade: Dict) -> Optional[CopyTrade]:
        """执行跟单"""
        size = float(trade.get("size", 0))
        price = float(trade.get("price", 0))
        
        copy_size = size * self.copy_ratio
        copy_size = max(self.min_size, min(copy_size, self.max_size))
        
        copy_trade = CopyTrade(
            original_trader=trader_address,
            copy_size=copy_size,
            copy_price=price,
            status="executed" if not self.simulation else "simulation"
        )
        
        self.copy_trades.append(copy_trade)
        logger.info(f"📋 跟单: {copy_size:.2f} @ {price:.4f}")
        
        if self.on_copy_trade:
            await self.on_copy_trade(copy_trade)
        
        return copy_trade
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            "target_traders": len(self.target_traders),
            "total_copies": len(self.copy_trades),
            "simulation": self.simulation
        }
    
    def get_trader_list(self) -> List[Dict]:
        """获取交易者列表"""
        return [
            {"address": info.address, "rank": info.rank, "pnl": info.pnl, "win_rate": info.win_rate}
            for info in self.trader_info.values()
        ]

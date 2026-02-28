"""
Flash Crash 策略
"""
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from config.settings import config
from core.client import PolymarketClient


@dataclass
class FlashCrashEvent:
    """Flash Crash 事件"""
    token_id: str
    side: str
    price_before: float
    price_after: float
    drop_pct: float
    timestamp: datetime = field(default_factory=datetime.now)


class FlashCrashStrategy:
    """Flash Crash 交易策略"""
    
    def __init__(self, client: PolymarketClient):
        self.client = client
        self.threshold = config.trading.FLASH_CRASH_THRESHOLD
        self.window = config.trading.FLASH_CRASH_WINDOW
        self.max_position = config.trading.MAX_POSITION_SIZE
        self.simulation = config.trading.SIMULATION_MODE
        
        self.price_history: Dict[str, List[tuple]] = {}
        self.on_crash_detected: Optional[Callable] = None
        self.on_trade_executed: Optional[Callable] = None
        
        self.stats = {
            "crashes_detected": 0,
            "trades_executed": 0,
            "total_pnl": 0.0
        }
    
    def _detect_crash(self, token_id: str) -> Optional[FlashCrashEvent]:
        """检测 Flash Crash"""
        history = self.price_history.get(token_id, [])
        if len(history) < 2:
            return None
        
        first_price = history[0][1]
        current_price = history[-1][1]
        
        if first_price > 0:
            drop_pct = abs(first_price - current_price) / first_price
            
            if drop_pct >= self.threshold:
                self.stats["crashes_detected"] += 1
                return FlashCrashEvent(
                    token_id=token_id,
                    side="BUY",
                    price_before=first_price,
                    price_after=current_price,
                    drop_pct=drop_pct
                )
        return None
    
    async def _handle_crash(self, event: FlashCrashEvent):
        """处理 Flash Crash"""
        logger.warning(f"🚨 Flash Crash: {event.drop_pct:.2%}")
        
        if self.on_crash_detected:
            await self.on_crash_detected(event)
        
        # 执行交易
        result = await self._execute_trade(event)
        if result:
            self.stats["trades_executed"] += 1
            if self.on_trade_executed:
                await self.on_trade_executed(result)
    
    async def _execute_trade(self, event: FlashCrashEvent) -> Optional[Dict]:
        """执行交易"""
        if self.simulation:
            logger.info(f"📝 模拟交易: 买入 @ {event.price_after:.4f}")
            return {"simulation": True, "price": event.price_after, "size": self.max_position}
        return None
    
    async def monitor_token(self, token_id: str, get_price_func: Callable):
        """监控单个 token"""
        while True:
            try:
                price = await get_price_func(token_id)
                if price > 0:
                    now = datetime.now().timestamp()
                    
                    if token_id not in self.price_history:
                        self.price_history[token_id] = []
                    
                    self.price_history[token_id].append((now, price))
                    
                    # 清理旧数据
                    cutoff = now - self.window
                    self.price_history[token_id] = [
                        (t, p) for t, p in self.price_history[token_id] if t > cutoff
                    ]
                    
                    # 检测
                    crash = self._detect_crash(token_id)
                    if crash:
                        await self._handle_crash(crash)
                
                import asyncio
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"监控错误: {e}")
                import asyncio
                await asyncio.sleep(5)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {**self.stats, "threshold": self.threshold, "window": self.window}

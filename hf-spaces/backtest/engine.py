"""
回测引擎
"""
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger

from config.settings import config
from analysis.technical import TechnicalAnalysis


@dataclass
class BacktestTrade:
    """回测交易"""
    timestamp: datetime
    side: str
    size: float
    price: float
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    """回测结果"""
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    win_rate: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[BacktestTrade] = field(default_factory=list)


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self):
        self.initial_capital = config.backtest.INITIAL_CAPITAL
        self.commission = config.backtest.COMMISSION
        self.ta = TechnicalAnalysis()
        
        self.capital = self.initial_capital
        self.position = None
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[float] = []
    
    def set_strategy(self, strategy: Callable):
        """设置策略"""
        self.strategy = strategy
    
    async def run_backtest(self, historical_data: List[Dict]) -> BacktestResult:
        """运行回测"""
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        
        for i, candle in enumerate(historical_data):
            self.equity_curve.append(self.capital)
            
            window = historical_data[:i+1]
            if len(window) < 30:
                continue
            
            prices = [c["price"] for c in window]
            
            if hasattr(self, 'strategy'):
                signal = await self.strategy(window, self.ta, {})
                if signal:
                    await self._execute_signal(signal, candle)
        
        # 平仓
        if self.position:
            await self._close_position(historical_data[-1], "End")
        
        return self._calculate_result()
    
    async def _execute_signal(self, signal: Dict, candle: Dict):
        """执行信号"""
        action = signal.get("action")
        
        if action == "BUY" and not self.position:
            price = candle["price"]
            size = min(signal.get("size", self.capital * 0.1), self.capital)
            
            self.position = {
                "entry_price": price,
                "size": size,
                "direction": signal.get("direction", "UP")
            }
            self.capital -= size
            
            self.trades.append(BacktestTrade(
                timestamp=datetime.now(),
                side="BUY",
                size=size,
                price=price,
                reason=signal.get("reason", "")
            ))
        
        elif action == "SELL" and self.position:
            await self._close_position(candle, signal.get("reason", ""))
    
    async def _close_position(self, candle: Dict, reason: str):
        """平仓"""
        if not self.position:
            return
        
        exit_price = candle["price"]
        entry_price = self.position["entry_price"]
        size = self.position["size"]
        
        pnl = (exit_price - entry_price) * size / entry_price
        pnl -= size * self.commission
        
        self.capital += size + pnl
        
        self.trades.append(BacktestTrade(
            timestamp=datetime.now(),
            side="SELL",
            size=size,
            price=exit_price,
            pnl=pnl,
            reason=reason
        ))
        
        self.position = None
    
    def _calculate_result(self) -> BacktestResult:
        """计算结果"""
        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]
        
        total_pnl = sum(t.pnl for t in self.trades)
        win_rate = len(winning) / len(self.trades) if self.trades else 0
        
        # 最大回撤
        max_dd = 0
        peak = self.initial_capital
        for eq in self.equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        
        return BacktestResult(
            initial_capital=self.initial_capital,
            final_capital=self.capital,
            total_trades=len(self.trades) // 2,
            winning_trades=len(winning) // 2,
            losing_trades=len(losing) // 2,
            total_pnl=total_pnl,
            win_rate=win_rate,
            max_drawdown=max_dd,
            sharpe_ratio=0.0,
            trades=self.trades
        )


# 预定义策略
async def combined_strategy(window: List[Dict], ta: TechnicalAnalysis, params: Dict) -> Optional[Dict]:
    """组合策略"""
    if len(window) < 30:
        return None
    
    prices = [c["price"] for c in window]
    signal = ta.get_combined_signal(prices)
    
    if signal["strength"] >= 0.6:
        return {
            "action": "BUY",
            "direction": signal["direction"],
            "size": 10,
            "reason": f"Technical: {signal['direction']}"
        }
    return None

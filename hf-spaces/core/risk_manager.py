"""
风险管理系统
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from loguru import logger

from config.settings import config


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Position:
    """持仓"""
    token_id: str
    side: str
    size: float
    entry_price: float
    current_price: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    @property
    def pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.size
    
    @property
    def pnl_pct(self) -> float:
        return self.pnl / (self.entry_price * self.size) if self.entry_price > 0 else 0


@dataclass
class RiskAlert:
    """风险警告"""
    level: RiskLevel
    message: str
    action: str
    timestamp: datetime = field(default_factory=datetime.now)


class RiskManager:
    """风险管理器"""
    
    def __init__(self):
        self.max_position = config.trading.MAX_POSITION_SIZE
        self.max_daily_loss = config.trading.MAX_DAILY_LOSS
        self.stop_loss_pct = config.trading.STOP_LOSS_PCT
        self.take_profit_pct = config.trading.TAKE_PROFIT_PCT
        
        self.positions: Dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.alerts: List[RiskAlert] = []
        
        self.on_stop_loss = None
        self.on_take_profit = None
    
    def check_can_trade(self, size: float) -> tuple:
        """检查是否可以交易"""
        if size > self.max_position:
            return False, f"仓位超过最大限制 ({size} > {self.max_position})"
        if self.daily_pnl < -self.max_daily_loss:
            return False, f"每日亏损已达上限"
        return True, "OK"
    
    def open_position(self, token_id: str, side: str, size: float, price: float) -> Position:
        """开仓"""
        position = Position(
            token_id=token_id,
            side=side,
            size=size,
            entry_price=price,
            current_price=price
        )
        self.positions[token_id] = position
        logger.info(f"📈 开仓: {side} {size} @ {price:.4f}")
        return position
    
    def update_position(self, token_id: str, current_price: float) -> Optional[RiskAlert]:
        """更新持仓价格"""
        if token_id not in self.positions:
            return None
        
        position = self.positions[token_id]
        position.current_price = current_price
        
        # 检查止损
        if position.pnl_pct <= -self.stop_loss_pct:
            alert = RiskAlert(
                level=RiskLevel.HIGH,
                message=f"触发止损: {position.pnl_pct:.2%}",
                action="CLOSE_POSITION"
            )
            self.alerts.append(alert)
            logger.warning(f"🚨 止损触发: {token_id[:20]}")
            return alert
        
        # 检查止盈
        if position.pnl_pct >= self.take_profit_pct:
            alert = RiskAlert(
                level=RiskLevel.LOW,
                message=f"触发止盈: {position.pnl_pct:.2%}",
                action="TAKE_PROFIT"
            )
            self.alerts.append(alert)
            logger.info(f"💰 止盈触发: {token_id[:20]}")
            return alert
        
        return None
    
    def close_position(self, token_id: str) -> Optional[Position]:
        """平仓"""
        if token_id not in self.positions:
            return None
        position = self.positions.pop(token_id)
        self.daily_pnl += position.pnl
        logger.info(f"📉 平仓: PnL = {position.pnl:.2f}")
        return position
    
    def get_risk_level(self) -> RiskLevel:
        """获取风险等级"""
        loss_ratio = abs(self.daily_pnl) / self.max_daily_loss if self.max_daily_loss > 0 else 0
        if loss_ratio >= 1.0:
            return RiskLevel.CRITICAL
        elif loss_ratio >= 0.75:
            return RiskLevel.HIGH
        elif loss_ratio >= 0.5:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    
    def get_portfolio_summary(self) -> Dict:
        """获取投资组合摘要"""
        return {
            "positions": len(self.positions),
            "total_pnl": sum(p.pnl for p in self.positions.values()),
            "daily_pnl": self.daily_pnl,
            "risk_level": self.get_risk_level().value
        }

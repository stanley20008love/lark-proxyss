"""
增强版风险管理系统 (Enhanced Risk Manager)

整合了 predict-fun-marketmaker 的风控功能：
- 当日亏损熔断
- 波动暂停机制
- 仓位管理
- 滑点控制
- 冷却时间
"""
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import deque
from loguru import logger


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitBreakerState(Enum):
    """熔断状态"""
    OPEN = "open"           # 开启（停止交易）
    HALF_OPEN = "half_open" # 半开（试探性恢复）
    CLOSED = "closed"       # 关闭（正常交易）


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


@dataclass
class RiskConfig:
    """风险管理配置"""
    # 仓位限制
    max_position_size: float = 100.0
    max_daily_loss: float = 50.0
    max_drawdown: float = 0.20          # 最大回撤 20%
    
    # 止损止盈
    stop_loss_pct: float = 0.30
    take_profit_pct: float = 0.20
    trailing_stop_pct: float = 0.10
    
    # 熔断设置
    circuit_breaker_threshold: float = 0.10  # 10% 亏损触发熔断
    circuit_breaker_cooldown: int = 3600      # 熔断冷却时间（秒）
    
    # 波动暂停
    volatility_threshold: float = 0.02        # 2% 波动阈值
    volatility_lookback: int = 10             # 波动检测窗口
    volatility_pause_duration: int = 300      # 波动暂停时长（秒）
    
    # 冷却时间
    cooldown_after_cancel: int = 4            # 撤单后冷却（秒）
    cooldown_after_trade: int = 10            # 交易后冷却（秒）
    
    # 滑点控制
    max_slippage_bps: float = 250.0           # 最大滑点


class EnhancedRiskManager:
    """增强版风险管理器"""
    
    def __init__(self, config: Optional[RiskConfig] = None):
        self.config = config or RiskConfig()
        
        # 持仓管理
        self.positions: Dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.peak_pnl = 0.0
        
        # 价格历史（用于波动检测）
        self.price_history: Dict[str, deque] = {}
        
        # 熔断状态
        self.circuit_breaker_state = CircuitBreaker.CLOSED
        self.circuit_breaker_triggered_at: Optional[datetime] = None
        
        # 波动暂停
        self.volatility_paused_until: Optional[datetime] = None
        
        # 冷却时间
        self.last_cancel_time: Optional[datetime] = None
        self.last_trade_time: Optional[datetime] = None
        
        # 警告历史
        self.alerts: List[RiskAlert] = []
        
        # 回调函数
        self.on_stop_loss: Optional[Callable] = None
        self.on_take_profit: Optional[Callable] = None
        self.on_circuit_breaker: Optional[Callable] = None
    
    def check_can_trade(self, size: float) -> tuple:
        """检查是否可以交易"""
        # 检查熔断状态
        if self.circuit_breaker_state == CircuitBreaker.OPEN:
            if self._can_attempt_recovery():
                self.circuit_breaker_state = CircuitBreaker.HALF_OPEN
                logger.info("🔄 熔断器进入半开状态，试探性恢复")
            else:
                return False, "熔断器已触发，交易暂停"
        
        # 检查波动暂停
        if self.volatility_paused_until and datetime.now() < self.volatility_paused_until:
            remaining = (self.volatility_paused_until - datetime.now()).seconds
            return False, f"波动暂停中，剩余 {remaining} 秒"
        
        # 检查冷却时间
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).seconds
            if elapsed < self.config.cooldown_after_trade:
                return False, f"交易冷却中，剩余 {self.config.cooldown_after_trade - elapsed} 秒"
        
        # 检查仓位限制
        if size > self.config.max_position_size:
            return False, f"仓位超过最大限制 ({size} > {self.config.max_position_size})"
        
        # 检查每日亏损
        if self.daily_pnl < -self.config.max_daily_loss:
            self._trigger_circuit_breaker("每日亏损达上限")
            return False, "每日亏损已达上限"
        
        # 检查最大回撤
        if self.peak_pnl > 0:
            drawdown = (self.peak_pnl - self.daily_pnl) / self.peak_pnl
            if drawdown > self.config.max_drawdown:
                self._trigger_circuit_breaker("最大回撤触发")
                return False, "最大回撤触发"
        
        return True, "OK"
    
    def check_can_cancel(self) -> tuple:
        """检查是否可以撤单"""
        if self.last_cancel_time:
            elapsed = (datetime.now() - self.last_cancel_time).seconds
            if elapsed < self.config.cooldown_after_cancel:
                return False, f"撤单冷却中，剩余 {self.config.cooldown_after_cancel - elapsed} 秒"
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
        self.last_trade_time = datetime.now()
        logger.info(f"📈 开仓: {side} {size} @ {price:.4f}")
        return position
    
    def update_position(self, token_id: str, current_price: float) -> Optional[RiskAlert]:
        """更新持仓价格"""
        if token_id not in self.positions:
            return None
        
        position = self.positions[token_id]
        old_price = position.current_price
        position.current_price = current_price
        
        # 更新价格历史
        self._update_price_history(token_id, current_price)
        
        # 检查波动
        self._check_volatility(token_id, old_price, current_price)
        
        # 检查止损
        if position.pnl_pct <= -self.config.stop_loss_pct:
            alert = RiskAlert(
                level=RiskLevel.HIGH,
                message=f"触发止损: {position.pnl_pct:.2%}",
                action="CLOSE_POSITION"
            )
            self.alerts.append(alert)
            logger.warning(f"🚨 止损触发: {token_id[:20]}")
            if self.on_stop_loss:
                self.on_stop_loss(position)
            return alert
        
        # 检查止盈
        if position.pnl_pct >= self.config.take_profit_pct:
            alert = RiskAlert(
                level=RiskLevel.LOW,
                message=f"触发止盈: {position.pnl_pct:.2%}",
                action="TAKE_PROFIT"
            )
            self.alerts.append(alert)
            logger.info(f"💰 止盈触发: {token_id[:20]}")
            if self.on_take_profit:
                self.on_take_profit(position)
            return alert
        
        # 检查移动止损
        if position.pnl_pct > 0.05:  # 有一定利润后启用移动止损
            trailing_stop_price = position.entry_price * (1 + position.pnl_pct - self.config.trailing_stop_pct)
            if current_price < trailing_stop_price:
                alert = RiskAlert(
                    level=RiskLevel.MEDIUM,
                    message=f"移动止损触发: 当前价格 {current_price:.4f}",
                    action="CLOSE_POSITION"
                )
                self.alerts.append(alert)
                return alert
        
        return None
    
    def close_position(self, token_id: str) -> Optional[Position]:
        """平仓"""
        if token_id not in self.positions:
            return None
        
        position = self.positions.pop(token_id)
        self.daily_pnl += position.pnl
        self.peak_pnl = max(self.peak_pnl, self.daily_pnl)
        self.last_trade_time = datetime.now()
        
        logger.info(f"📉 平仓: PnL = {position.pnl:.2f}")
        
        # 检查是否需要触发熔断
        if self.daily_pnl < -self.config.circuit_breaker_threshold * self.config.max_daily_loss:
            self._trigger_circuit_breaker("连续亏损触发熔断")
        
        return position
    
    def record_cancel(self):
        """记录撤单"""
        self.last_cancel_time = datetime.now()
    
    def _update_price_history(self, token_id: str, price: float):
        """更新价格历史"""
        if token_id not in self.price_history:
            self.price_history[token_id] = deque(maxlen=100)
        self.price_history[token_id].append({
            "price": price,
            "timestamp": datetime.now()
        })
    
    def _check_volatility(self, token_id: str, old_price: float, new_price: float):
        """检查波动"""
        if old_price == 0:
            return
        
        change = abs(new_price - old_price) / old_price
        
        if change > self.config.volatility_threshold:
            self.volatility_paused_until = datetime.now() + timedelta(seconds=self.config.volatility_pause_duration)
            logger.warning(f"⚠️ 波动检测: {change:.2%}，暂停 {self.config.volatility_pause_duration} 秒")
    
    def _trigger_circuit_breaker(self, reason: str):
        """触发熔断"""
        self.circuit_breaker_state = CircuitBreaker.OPEN
        self.circuit_breaker_triggered_at = datetime.now()
        
        alert = RiskAlert(
            level=RiskLevel.CRITICAL,
            message=f"熔断触发: {reason}",
            action="STOP_ALL_TRADING"
        )
        self.alerts.append(alert)
        
        logger.critical(f"🔴 熔断触发: {reason}")
        
        if self.on_circuit_breaker:
            self.on_circuit_breaker(reason)
    
    def _can_attempt_recovery(self) -> bool:
        """检查是否可以尝试恢复"""
        if not self.circuit_breaker_triggered_at:
            return False
        
        elapsed = (datetime.now() - self.circuit_breaker_triggered_at).seconds
        return elapsed >= self.config.circuit_breaker_cooldown
    
    def reset_circuit_breaker(self):
        """重置熔断器"""
        self.circuit_breaker_state = CircuitBreaker.CLOSED
        self.circuit_breaker_triggered_at = None
        logger.info("✅ 熔断器已重置")
    
    def get_risk_level(self) -> RiskLevel:
        """获取风险等级"""
        # 检查熔断
        if self.circuit_breaker_state == CircuitBreaker.OPEN:
            return RiskLevel.CRITICAL
        
        # 检查波动暂停
        if self.volatility_paused_until and datetime.now() < self.volatility_paused_until:
            return RiskLevel.HIGH
        
        # 检查亏损比例
        loss_ratio = abs(self.daily_pnl) / self.config.max_daily_loss if self.config.max_daily_loss > 0 else 0
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
            "peak_pnl": self.peak_pnl,
            "risk_level": self.get_risk_level().value,
            "circuit_breaker": self.circuit_breaker_state.value,
            "volatility_paused": self.volatility_paused_until and datetime.now() < self.volatility_paused_until,
            "alerts_count": len(self.alerts)
        }
    
    def check_all_positions(self, prices: Dict[str, float]) -> List[RiskAlert]:
        """检查所有持仓"""
        alerts = []
        for token_id, position in self.positions.items():
            if token_id in prices:
                alert = self.update_position(token_id, prices[token_id])
                if alert:
                    alerts.append(alert)
        return alerts
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "daily_pnl": round(self.daily_pnl, 2),
            "peak_pnl": round(self.peak_pnl, 2),
            "positions": len(self.positions),
            "risk_level": self.get_risk_level().value,
            "circuit_breaker": self.circuit_breaker_state.value,
            "total_alerts": len(self.alerts),
            "alerts_today": len([a for a in self.alerts if a.timestamp.date() == datetime.now().date()])
        }


# 全局单例
enhanced_risk_manager = EnhancedRiskManager()

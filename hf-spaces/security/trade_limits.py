"""
交易限制与熔断模块 (Trade Limits & Circuit Breaker)

实现多层次的交易安全限制:
1. 单笔交易限制
2. 每日累计限制
3. 亏损熔断
4. 异常检测熔断
5. 时间锁限制
"""
import os
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio
import logging

logger = logging.getLogger(__name__)


class CircuitBreakerStatus(Enum):
    """熔断状态"""
    NORMAL = "normal"              # 正常运行
    WARNING = "warning"            # 警告状态
    TRIGGERED = "triggered"        # 已触发熔断
    COOLDOWN = "cooldown"          # 冷却中
    DISABLED = "disabled"          # 已禁用


@dataclass
class TradeRecord:
    """交易记录"""
    timestamp: datetime
    market_id: str
    side: str
    amount: float
    price: float
    pnl: float = 0.0
    status: str = "completed"


@dataclass
class LimitConfig:
    """限制配置"""
    # 单笔限制
    max_single_trade_usd: float = 100.0        # 单笔最大交易金额
    max_single_trade_pct: float = 0.10         # 单笔最大占热钱包比例
    
    # 每日限制
    max_daily_trades: int = 100                 # 每日最大交易次数
    max_daily_volume_usd: float = 5000.0       # 每日最大交易量
    max_daily_volume_pct: float = 0.50         # 每日最大占热钱包比例
    
    # 亏损限制
    max_daily_loss_usd: float = 100.0          # 每日最大亏损金额
    max_daily_loss_pct: float = 0.05           # 每日最大亏损比例
    max_drawdown_pct: float = 0.20             # 最大回撤比例
    
    # 熔断设置
    circuit_breaker_threshold: float = 0.10    # 熔断触发阈值 (10%亏损)
    circuit_breaker_cooldown: int = 3600       # 熔断冷却时间 (秒)
    
    # 异常检测
    max_trades_per_minute: int = 10            # 每分钟最大交易数
    max_unusual_size_multiplier: float = 5.0   # 异常交易倍数
    
    # 时间锁
    withdrawal_delay_seconds: int = 300        # 提现延迟 (5分钟)
    large_trade_delay_seconds: int = 60        # 大额交易延迟 (1分钟)
    
    @classmethod
    def from_env(cls) -> 'LimitConfig':
        """从环境变量加载配置"""
        return cls(
            max_single_trade_usd=float(os.getenv("MAX_SINGLE_TRADE_USD", "100")),
            max_daily_loss_usd=float(os.getenv("MAX_DAILY_LOSS_USD", "100")),
            max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "0.05")),
            circuit_breaker_threshold=float(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "0.10")),
            circuit_breaker_cooldown=int(os.getenv("CIRCUIT_BREAKER_COOLDOWN", "3600")),
        )


class TradeLimiter:
    """
    交易限制器
    
    检查每笔交易是否符合安全限制
    """
    
    def __init__(self, config: Optional[LimitConfig] = None, hot_wallet_balance: float = 1000.0):
        self.config = config or LimitConfig.from_env()
        self.hot_wallet_balance = hot_wallet_balance
        
        # 交易记录
        self.trades: List[TradeRecord] = []
        self.daily_trades: List[TradeRecord] = []
        
        # 统计
        self.daily_pnl = 0.0
        self.peak_value = hot_wallet_balance
        self.current_drawdown = 0.0
        
        # 时间窗口
        self.trades_last_minute: List[datetime] = []
        
    def update_wallet_balance(self, balance: float):
        """更新钱包余额"""
        self.hot_wallet_balance = balance
        if balance > self.peak_value:
            self.peak_value = balance
        self.current_drawdown = (self.peak_value - balance) / self.peak_value if self.peak_value > 0 else 0
    
    def check_trade(self, amount: float, market_id: str = "", side: str = "") -> Dict[str, Any]:
        """
        检查交易是否允许
        
        Returns:
            {"allowed": bool, "reason": str, "warnings": list}
        """
        result = {
            "allowed": True,
            "reason": "",
            "warnings": [],
            "checks": {}
        }
        
        now = datetime.now()
        
        # 清理过期记录
        self._cleanup_old_records(now)
        
        # 1. 单笔金额检查
        single_check = self._check_single_trade(amount)
        result["checks"]["single_trade"] = single_check
        if not single_check["passed"]:
            result["allowed"] = False
            result["reason"] = single_check["reason"]
            return result
        
        # 2. 每日交易次数检查
        daily_count_check = self._check_daily_trades()
        result["checks"]["daily_trades"] = daily_count_check
        if not daily_count_check["passed"]:
            result["allowed"] = False
            result["reason"] = daily_count_check["reason"]
            return result
        
        # 3. 每日交易量检查
        daily_volume_check = self._check_daily_volume(amount)
        result["checks"]["daily_volume"] = daily_volume_check
        if not daily_volume_check["passed"]:
            result["allowed"] = False
            result["reason"] = daily_volume_check["reason"]
            return result
        
        # 4. 每日亏损检查
        loss_check = self._check_daily_loss()
        result["checks"]["daily_loss"] = loss_check
        if not loss_check["passed"]:
            result["allowed"] = False
            result["reason"] = loss_check["reason"]
            return result
        
        # 5. 回撤检查
        drawdown_check = self._check_drawdown()
        result["checks"]["drawdown"] = drawdown_check
        if not drawdown_check["passed"]:
            result["allowed"] = False
            result["reason"] = drawdown_check["reason"]
            return result
        
        # 6. 高频交易检查
        frequency_check = self._check_frequency()
        result["checks"]["frequency"] = frequency_check
        if not frequency_check["passed"]:
            result["warnings"].append(frequency_check["reason"])
        
        # 7. 异常金额检查
        unusual_check = self._check_unusual_size(amount)
        result["checks"]["unusual_size"] = unusual_check
        if not unusual_check["passed"]:
            result["warnings"].append(unusual_check["reason"])
        
        return result
    
    def _check_single_trade(self, amount: float) -> Dict:
        """检查单笔交易"""
        if amount > self.config.max_single_trade_usd:
            return {
                "passed": False,
                "reason": f"单笔金额 ${amount:.2f} 超过限制 ${self.config.max_single_trade_usd:.2f}"
            }
        
        if self.hot_wallet_balance > 0:
            pct = amount / self.hot_wallet_balance
            if pct > self.config.max_single_trade_pct:
                return {
                    "passed": False,
                    "reason": f"单笔占比 {pct:.1%} 超过限制 {self.config.max_single_trade_pct:.1%}"
                }
        
        return {"passed": True, "reason": ""}
    
    def _check_daily_trades(self) -> Dict:
        """检查每日交易次数"""
        if len(self.daily_trades) >= self.config.max_daily_trades:
            return {
                "passed": False,
                "reason": f"每日交易次数 {len(self.daily_trades)} 已达上限 {self.config.max_daily_trades}"
            }
        return {"passed": True, "reason": ""}
    
    def _check_daily_volume(self, amount: float) -> Dict:
        """检查每日交易量"""
        today_volume = sum(t.amount for t in self.daily_trades)
        if today_volume + amount > self.config.max_daily_volume_usd:
            return {
                "passed": False,
                "reason": f"每日交易量将达 ${today_volume + amount:.2f}，超过限制 ${self.config.max_daily_volume_usd:.2f}"
            }
        
        if self.hot_wallet_balance > 0:
            pct = (today_volume + amount) / self.hot_wallet_balance
            if pct > self.config.max_daily_volume_pct:
                return {
                    "passed": False,
                    "reason": f"每日交易量占比 {pct:.1%} 超过限制 {self.config.max_daily_volume_pct:.1%}"
                }
        
        return {"passed": True, "reason": ""}
    
    def _check_daily_loss(self) -> Dict:
        """检查每日亏损"""
        if self.daily_pnl <= -self.config.max_daily_loss_usd:
            return {
                "passed": False,
                "reason": f"每日亏损 ${abs(self.daily_pnl):.2f} 已达上限 ${self.config.max_daily_loss_usd:.2f}"
            }
        
        if self.hot_wallet_balance > 0:
            loss_pct = abs(self.daily_pnl) / self.hot_wallet_balance
            if loss_pct >= self.config.max_daily_loss_pct:
                return {
                    "passed": False,
                    "reason": f"每日亏损比例 {loss_pct:.1%} 已达上限 {self.config.max_daily_loss_pct:.1%}"
                }
        
        return {"passed": True, "reason": ""}
    
    def _check_drawdown(self) -> Dict:
        """检查回撤"""
        if self.current_drawdown >= self.config.max_drawdown_pct:
            return {
                "passed": False,
                "reason": f"当前回撤 {self.current_drawdown:.1%} 已达上限 {self.config.max_drawdown_pct:.1%}"
            }
        return {"passed": True, "reason": ""}
    
    def _check_frequency(self) -> Dict:
        """检查交易频率"""
        now = datetime.now()
        one_minute_ago = now - timedelta(minutes=1)
        recent = [t for t in self.trades_last_minute if t > one_minute_ago]
        
        if len(recent) >= self.config.max_trades_per_minute:
            return {
                "passed": False,
                "reason": f"交易频率过高: {len(recent)} 笔/分钟"
            }
        return {"passed": True, "reason": ""}
    
    def _check_unusual_size(self, amount: float) -> Dict:
        """检查异常金额"""
        if len(self.daily_trades) < 3:
            return {"passed": True, "reason": ""}
        
        avg_amount = sum(t.amount for t in self.daily_trades) / len(self.daily_trades)
        if amount > avg_amount * self.config.max_unusual_size_multiplier:
            return {
                "passed": False,
                "reason": f"交易金额异常: ${amount:.2f} 超过平均值 {self.config.max_unusual_size_multiplier}x"
            }
        return {"passed": True, "reason": ""}
    
    def record_trade(self, trade: TradeRecord):
        """记录交易"""
        self.trades.append(trade)
        self.daily_trades.append(trade)
        self.trades_last_minute.append(trade.timestamp)
        self.daily_pnl += trade.pnl
        
        logger.info(f"📝 交易记录: {trade.market_id} {trade.side} ${trade.amount:.2f} PnL: ${trade.pnl:.2f}")
    
    def _cleanup_old_records(self, now: datetime):
        """清理过期记录"""
        # 清理每分钟记录
        one_minute_ago = now - timedelta(minutes=1)
        self.trades_last_minute = [t for t in self.trades_last_minute if t > one_minute_ago]
        
        # 清理每日记录 (跨日)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.daily_trades = [t for t in self.daily_trades if t.timestamp >= today_start]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_trades": len(self.trades),
            "daily_trades": len(self.daily_trades),
            "daily_pnl": self.daily_pnl,
            "peak_value": self.peak_value,
            "current_drawdown": f"{self.current_drawdown:.1%}",
            "hot_wallet_balance": self.hot_wallet_balance,
            "limits": {
                "max_single_trade": self.config.max_single_trade_usd,
                "max_daily_trades": self.config.max_daily_trades,
                "max_daily_loss": self.config.max_daily_loss_usd
            }
        }


class CircuitBreaker:
    """
    熔断器
    
    在异常情况下停止交易
    """
    
    def __init__(self, config: Optional[LimitConfig] = None):
        self.config = config or LimitConfig.from_env()
        self.status = CircuitBreakerStatus.NORMAL
        self.triggered_at: Optional[datetime] = None
        self.trigger_reason: str = ""
        self.trigger_count: int = 0
        self._resume_at: Optional[datetime] = None
        
    def check(self, trade_limiter: TradeLimiter) -> Dict:
        """
        检查是否应该触发熔断
        
        Returns:
            {"tripped": bool, "status": str, "reason": str}
        """
        result = {
            "tripped": False,
            "status": self.status.value,
            "reason": ""
        }
        
        # 如果已禁用，直接返回
        if self.status == CircuitBreakerStatus.DISABLED:
            result["tripped"] = True
            result["reason"] = "熔断器已禁用"
            return result
        
        # 如果在冷却期
        if self.status == CircuitBreakerStatus.COOLDOWN:
            if self._resume_at and datetime.now() < self._resume_at:
                remaining = (self._resume_at - datetime.now()).total_seconds()
                result["tripped"] = True
                result["reason"] = f"冷却中，剩余 {remaining:.0f} 秒"
                return result
            else:
                self.status = CircuitBreakerStatus.NORMAL
                logger.info("✅ 熔断器冷却完成，恢复正常")
        
        # 检查触发条件
        stats = trade_limiter.get_stats()
        
        # 亏损比例检查
        if abs(trade_limiter.daily_pnl) / trade_limiter.hot_wallet_balance >= self.config.circuit_breaker_threshold:
            self._trigger("每日亏损达到熔断阈值")
            result["tripped"] = True
            result["reason"] = self.trigger_reason
            result["status"] = self.status.value
            return result
        
        # 回撤检查
        if trade_limiter.current_drawdown >= self.config.circuit_breaker_threshold:
            self._trigger("回撤达到熔断阈值")
            result["tripped"] = True
            result["reason"] = self.trigger_reason
            result["status"] = self.status.value
            return result
        
        # 警告状态
        if abs(trade_limiter.daily_pnl) / trade_limiter.hot_wallet_balance >= self.config.circuit_breaker_threshold * 0.7:
            self.status = CircuitBreakerStatus.WARNING
            result["reason"] = "接近熔断阈值"
        
        return result
    
    def _trigger(self, reason: str):
        """触发熔断"""
        self.status = CircuitBreakerStatus.TRIGGERED
        self.triggered_at = datetime.now()
        self.trigger_reason = reason
        self.trigger_count += 1
        self._resume_at = datetime.now() + timedelta(seconds=self.config.circuit_breaker_cooldown)
        
        logger.warning(f"🚨 熔断触发: {reason}")
        logger.warning(f"   冷却时间: {self.config.circuit_breaker_cooldown} 秒")
    
    def manual_trigger(self, reason: str = "手动触发"):
        """手动触发熔断"""
        self._trigger(reason)
    
    def reset(self):
        """重置熔断器"""
        self.status = CircuitBreakerStatus.NORMAL
        self.triggered_at = None
        self.trigger_reason = ""
        self._resume_at = None
        logger.info("✅ 熔断器已重置")
    
    def disable(self):
        """禁用熔断器"""
        self.status = CircuitBreakerStatus.DISABLED
        logger.warning("⚠️ 熔断器已禁用")
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            "status": self.status.value,
            "triggered_at": self.triggered_at.isoformat() if self.triggered_at else None,
            "trigger_reason": self.trigger_reason,
            "trigger_count": self.trigger_count,
            "cooldown_remaining": (self._resume_at - datetime.now()).total_seconds() if self._resume_at and datetime.now() < self._resume_at else 0
        }


class TransactionSecurity:
    """
    交易安全管理器
    
    整合所有安全检查
    """
    
    def __init__(self, config: Optional[LimitConfig] = None, hot_wallet_balance: float = 1000.0):
        self.config = config or LimitConfig.from_env()
        self.trade_limiter = TradeLimiter(self.config, hot_wallet_balance)
        self.circuit_breaker = CircuitBreaker(self.config)
        
        # 安全日志
        self.security_log: List[Dict] = []
        
    def validate_transaction(self, amount: float, market_id: str = "", side: str = "") -> Dict:
        """
        验证交易安全性
        
        Returns:
            {"approved": bool, "reason": str, "checks": dict, "warnings": list}
        """
        result = {
            "approved": False,
            "reason": "",
            "checks": {},
            "warnings": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # 记录验证请求
        self._log_security_event("validation_request", {
            "amount": amount,
            "market_id": market_id,
            "side": side
        })
        
        # 1. 检查熔断器
        cb_result = self.circuit_breaker.check(self.trade_limiter)
        result["checks"]["circuit_breaker"] = cb_result
        
        if cb_result["tripped"]:
            result["reason"] = f"熔断器: {cb_result['reason']}"
            self._log_security_event("rejected", {"reason": result["reason"]})
            return result
        
        # 2. 检查交易限制
        trade_result = self.trade_limiter.check_trade(amount, market_id, side)
        result["checks"]["trade_limits"] = trade_result
        
        if not trade_result["allowed"]:
            result["reason"] = trade_result["reason"]
            self._log_security_event("rejected", {"reason": result["reason"]})
            return result
        
        result["warnings"] = trade_result.get("warnings", [])
        result["approved"] = True
        
        self._log_security_event("approved", {"amount": amount})
        return result
    
    def record_transaction(self, market_id: str, side: str, amount: float, price: float, pnl: float = 0):
        """记录交易"""
        trade = TradeRecord(
            timestamp=datetime.now(),
            market_id=market_id,
            side=side,
            amount=amount,
            price=price,
            pnl=pnl
        )
        self.trade_limiter.record_trade(trade)
    
    def update_balance(self, balance: float):
        """更新余额"""
        self.trade_limiter.update_wallet_balance(balance)
    
    def emergency_stop(self, reason: str = "紧急停止"):
        """紧急停止"""
        self.circuit_breaker.manual_trigger(reason)
        self._log_security_event("emergency_stop", {"reason": reason})
    
    def _log_security_event(self, event_type: str, data: Dict):
        """记录安全事件"""
        self.security_log.append({
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "data": data
        })
    
    def get_security_report(self) -> Dict:
        """获取安全报告"""
        return {
            "circuit_breaker": self.circuit_breaker.get_status(),
            "trade_stats": self.trade_limiter.get_stats(),
            "recent_events": self.security_log[-20:],
            "config": {
                "max_single_trade": self.config.max_single_trade_usd,
                "max_daily_loss": self.config.max_daily_loss_usd,
                "circuit_breaker_threshold": f"{self.config.circuit_breaker_threshold:.0%}"
            }
        }


# 全局安全实例
transaction_security = TransactionSecurity()

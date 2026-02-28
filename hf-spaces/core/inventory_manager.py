"""
智能库存管理模块 (Smart Inventory Manager)

基于风险和收益的智能持仓管理
- 动态风险等级评估
- 自动对冲建议
- 组合风险计算
"""
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque
from loguru import logger


class RiskLevel(Enum):
    """风险等级"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Urgency(Enum):
    """紧急程度"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class InventoryPosition:
    """库存持仓"""
    token_id: str
    yes_amount: float = 0.0
    no_amount: float = 0.0
    net_exposure: float = 0.0          # 净敞口
    max_position: float = 100.0
    risk_level: RiskLevel = RiskLevel.LOW
    unrealized_pnl: float = 0.0
    avg_entry_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class HedgeRecommendation:
    """对冲建议"""
    should_hedge: bool
    side: Optional[Literal["BUY", "SELL"]]
    amount: float
    reason: str
    urgency: Urgency
    target_price: Optional[float] = None


@dataclass
class InventoryConfig:
    """库存管理配置"""
    max_position: float = 100.0
    max_net_exposure: float = 50.0
    hedge_threshold: float = 0.7        # 触发对冲的阈值（70%）
    hedge_ratio: float = 0.5            # 对冲比例（50%）
    risk_multiplier: float = 1.5
    enable_auto_hedge: bool = True
    volatility_threshold: float = 0.02  # 波动阈值


class SmartInventoryManager:
    """智能库存管理器"""
    
    def __init__(self, config: Optional[InventoryConfig] = None):
        self.config = config or InventoryConfig()
        self.positions: Dict[str, InventoryPosition] = {}
        self.price_history: Dict[str, deque] = {}  # 价格历史
        self.hedge_history: List[Dict] = []        # 对冲历史
    
    def update_position(
        self,
        token_id: str,
        yes_amount: float,
        no_amount: float,
        current_price: float,
        avg_entry_price: float = 0.0
    ) -> InventoryPosition:
        """
        更新持仓
        """
        net_exposure = yes_amount - no_amount
        max_pos = self.config.max_position
        exposure_ratio = abs(net_exposure) / max_pos if max_pos > 0 else 0
        
        # 确定风险等级
        risk_level = RiskLevel.LOW
        if exposure_ratio > 0.9:
            risk_level = RiskLevel.CRITICAL
        elif exposure_ratio > 0.7:
            risk_level = RiskLevel.HIGH
        elif exposure_ratio > 0.5:
            risk_level = RiskLevel.MEDIUM
        
        # 计算未实现盈亏
        unrealized_pnl = (current_price - avg_entry_price) * net_exposure if avg_entry_price > 0 else 0
        
        position = InventoryPosition(
            token_id=token_id,
            yes_amount=yes_amount,
            no_amount=no_amount,
            net_exposure=net_exposure,
            max_position=max_pos,
            risk_level=risk_level,
            unrealized_pnl=unrealized_pnl,
            avg_entry_price=avg_entry_price
        )
        
        self.positions[token_id] = position
        self._update_price_history(token_id, current_price)
        
        return position
    
    def get_hedge_recommendation(self, token_id: str) -> HedgeRecommendation:
        """
        获取对冲建议
        """
        position = self.positions.get(token_id)
        if not position:
            return HedgeRecommendation(
                should_hedge=False,
                side=None,
                amount=0,
                reason="无持仓",
                urgency=Urgency.LOW
            )
        
        exposure_ratio = abs(position.net_exposure) / position.max_position if position.max_position > 0 else 0
        
        # 检查是否需要对冲
        if exposure_ratio < self.config.hedge_threshold:
            return HedgeRecommendation(
                should_hedge=False,
                side=None,
                amount=0,
                reason=f"敞口在安全范围内 ({exposure_ratio:.1%})",
                urgency=Urgency.LOW
            )
        
        # 计算对冲方向
        side = "SELL" if position.net_exposure > 0 else "BUY"
        
        # 计算对冲数量
        hedge_amount = abs(position.net_exposure) * self.config.hedge_ratio
        
        # 确定紧急程度
        urgency = Urgency.LOW
        if position.risk_level == RiskLevel.CRITICAL:
            urgency = Urgency.HIGH
        elif position.risk_level == RiskLevel.HIGH:
            urgency = Urgency.MEDIUM
        
        # 生成原因
        reason = self._generate_hedge_reason(position, exposure_ratio)
        
        return HedgeRecommendation(
            should_hedge=True,
            side=side,
            amount=hedge_amount,
            reason=reason,
            urgency=urgency
        )
    
    def get_all_hedge_recommendations(self) -> List[Dict]:
        """
        获取所有对冲建议
        """
        recommendations = []
        
        for token_id in self.positions:
            rec = self.get_hedge_recommendation(token_id)
            if rec.should_hedge:
                recommendations.append({
                    "token_id": token_id,
                    "recommendation": rec
                })
        
        # 按紧急程度排序
        urgency_order = {Urgency.HIGH: 3, Urgency.MEDIUM: 2, Urgency.LOW: 1}
        recommendations.sort(
            key=lambda x: urgency_order[x["recommendation"].urgency],
            reverse=True
        )
        
        return recommendations
    
    def calculate_portfolio_risk(self) -> Dict:
        """
        计算组合风险
        """
        total_exposure = 0.0
        net_exposure = 0.0
        max_exposure = 0.0
        
        for position in self.positions.values():
            exposure = abs(position.net_exposure)
            total_exposure += exposure
            net_exposure += position.net_exposure
            max_exposure = max(max_exposure, exposure)
        
        total_max = len(self.positions) * self.config.max_position
        exposure_ratio = total_exposure / max(1, total_max)
        net_ratio = abs(net_exposure) / max(1, total_max)
        
        # 风险评分 (0-100)
        risk_score = min(100, (exposure_ratio * 50 + net_ratio * 50))
        
        # 确定风险等级
        risk_level = RiskLevel.LOW
        if risk_score > 80:
            risk_level = RiskLevel.CRITICAL
        elif risk_score > 60:
            risk_level = RiskLevel.HIGH
        elif risk_score > 40:
            risk_level = RiskLevel.MEDIUM
        
        # 计算分散度（基于赫芬达尔指数）
        concentrations = []
        for position in self.positions.values():
            concentration = abs(position.net_exposure) / max(1, total_exposure)
            concentrations.append(concentration)
        
        hhi = sum(c * c for c in concentrations)
        diversification_ratio = 1 - hhi
        
        return {
            "total_exposure": total_exposure,
            "net_exposure": net_exposure,
            "risk_score": risk_score,
            "risk_level": risk_level.value,
            "diversification_ratio": round(diversification_ratio, 3),
            "exposure_ratio": round(exposure_ratio, 3)
        }
    
    def calculate_price_volatility(self, token_id: str) -> float:
        """
        计算价格波动性
        """
        history = self.price_history.get(token_id)
        if not history or len(history) < 2:
            return 0.0
        
        history_list = list(history)
        returns = []
        for i in range(1, len(history_list)):
            if history_list[i-1] > 0:
                returns.append((history_list[i] - history_list[i-1]) / history_list[i-1])
        
        if not returns:
            return 0.0
        
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / len(returns)
        return variance ** 0.5
    
    def get_stats(self) -> Dict:
        """
        获取持仓统计
        """
        total_yes = sum(p.yes_amount for p in self.positions.values())
        total_no = sum(p.no_amount for p in self.positions.values())
        total_net = sum(p.net_exposure for p in self.positions.values())
        total_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        
        risk_distribution = {level.value: 0 for level in RiskLevel}
        for position in self.positions.values():
            risk_distribution[position.risk_level.value] += 1
        
        return {
            "total_positions": len(self.positions),
            "total_yes_amount": total_yes,
            "total_no_amount": total_no,
            "total_net_exposure": total_net,
            "total_unrealized_pnl": round(total_pnl, 2),
            "risk_distribution": risk_distribution
        }
    
    def execute_hedge(self, token_id: str, side: str, amount: float, price: float) -> Dict:
        """
        执行对冲
        """
        position = self.positions.get(token_id)
        if not position:
            return {"success": False, "reason": "无持仓"}
        
        # 记录对冲历史
        hedge_record = {
            "token_id": token_id,
            "side": side,
            "amount": amount,
            "price": price,
            "timestamp": datetime.now().isoformat(),
            "exposure_before": position.net_exposure
        }
        
        self.hedge_history.append(hedge_record)
        
        # 更新持仓
        if side == "SELL":
            if position.net_exposure > 0:  # YES 过多，卖出 YES
                position.yes_amount -= amount
            else:  # NO 过多，卖出 NO
                position.no_amount -= amount
        else:  # BUY
            if position.net_exposure < 0:  # NO 过多，买入 YES
                position.yes_amount += amount
            else:  # YES 过多，买入 NO
                position.no_amount += amount
        
        # 重新计算净敞口和风险等级
        position.net_exposure = position.yes_amount - position.no_amount
        exposure_ratio = abs(position.net_exposure) / position.max_position if position.max_position > 0 else 0
        
        if exposure_ratio > 0.9:
            position.risk_level = RiskLevel.CRITICAL
        elif exposure_ratio > 0.7:
            position.risk_level = RiskLevel.HIGH
        elif exposure_ratio > 0.5:
            position.risk_level = RiskLevel.MEDIUM
        else:
            position.risk_level = RiskLevel.LOW
        
        hedge_record["exposure_after"] = position.net_exposure
        hedge_record["success"] = True
        
        logger.info(f"🔄 对冲执行: {side} {amount} @ {price:.4f}, 新敞口: {position.net_exposure:.2f}")
        
        return {"success": True, "record": hedge_record}
    
    def _update_price_history(self, token_id: str, price: float):
        """更新价格历史"""
        if token_id not in self.price_history:
            self.price_history[token_id] = deque(maxlen=50)
        
        self.price_history[token_id].append(price)
    
    def _generate_hedge_reason(self, position: InventoryPosition, exposure_ratio: float) -> str:
        """生成对冲原因"""
        reasons = []
        
        if position.risk_level == RiskLevel.CRITICAL:
            reasons.append("敞口接近临界值")
        elif position.risk_level == RiskLevel.HIGH:
            reasons.append("敞口过高")
        
        if position.unrealized_pnl < -10:
            reasons.append(f"未实现亏损: ${position.unrealized_pnl:.2f}")
        
        # 检查价格波动
        volatility = self.calculate_price_volatility(position.token_id)
        if volatility > self.config.volatility_threshold:
            reasons.append("高波动性")
        
        if not reasons:
            reasons.append(f"敞口占比 {exposure_ratio:.0%}")
        
        return "; ".join(reasons)
    
    def remove_position(self, token_id: str):
        """移除持仓"""
        if token_id in self.positions:
            del self.positions[token_id]
        if token_id in self.price_history:
            del self.price_history[token_id]
    
    def clear(self):
        """清空所有持仓"""
        self.positions.clear()
        self.price_history.clear()
        self.hedge_history.clear()
    
    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)


# 全局单例
smart_inventory_manager = SmartInventoryManager()

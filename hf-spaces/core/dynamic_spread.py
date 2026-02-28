"""
动态价差调整模块 (Dynamic Spread Calculator)

基于市场状况自动调整价差以优化收益和风险
- 波动性感知
- 流动性评估
- 买卖压力分析
- 订单簿失衡检测
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from loguru import logger


@dataclass
class MarketCondition:
    """市场状况"""
    volatility: float = 0.0       # 波动性
    liquidity: float = 0.0        # 流动性
    spread: float = 0.0           # 当前价差
    volume: float = 0.0           # 成交量
    pressure: float = 0.0         # 买卖压力 (-1 到 1)
    depth_trend: float = 1.0      # 深度趋势
    imbalance: float = 0.0        # 订单簿失衡 (-1 到 1)


@dataclass
class SpreadAdjustment:
    """价差调整"""
    new_spread: float
    confidence: float              # 0-1, 调整的置信度
    reason: str                    # 调整原因
    factors: Dict[str, float]      # 各因素的贡献
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class DynamicSpreadConfig:
    """动态价差配置"""
    base_spread: float = 0.02
    min_spread: float = 0.005
    max_spread: float = 0.10
    volatility_weight: float = 0.30
    liquidity_weight: float = 0.25
    volume_weight: float = 0.20
    pressure_weight: float = 0.15
    adjustment_speed: float = 0.5      # 调整速度 (0-1)
    confidence_threshold: float = 0.6  # 最小置信度


class DynamicSpreadCalculator:
    """动态价差计算器"""
    
    def __init__(self, config: Optional[DynamicSpreadConfig] = None):
        self.config = config or DynamicSpreadConfig()
        self.spread_history: Dict[str, deque] = {}
        self.adjustment_count = 0
        self.total_adjustments = 0.0
    
    def calculate_adjustment(
        self,
        market_id: str,
        condition: MarketCondition,
        current_spread: float
    ) -> SpreadAdjustment:
        """
        计算动态价差调整
        """
        factors: Dict[str, float] = {}
        
        # 1. 波动性因素
        volatility_factor = self._calculate_volatility_factor(condition.volatility)
        factors["volatility"] = volatility_factor
        
        # 2. 流动性因素
        liquidity_factor = self._calculate_liquidity_factor(condition.liquidity)
        factors["liquidity"] = liquidity_factor
        
        # 3. 成交量因素
        volume_factor = self._calculate_volume_factor(condition.volume)
        factors["volume"] = volume_factor
        
        # 4. 压力因素
        pressure_factor = self._calculate_pressure_factor(condition.pressure)
        factors["pressure"] = pressure_factor
        
        # 5. 深度趋势因素
        depth_factor = self._calculate_depth_trend_factor(condition.depth_trend)
        factors["depth_trend"] = depth_factor
        
        # 6. 订单簿失衡因素
        imbalance_factor = self._calculate_imbalance_factor(condition.imbalance)
        factors["imbalance"] = imbalance_factor
        
        # 计算加权调整
        weighted_adjustment = (
            volatility_factor * self.config.volatility_weight +
            liquidity_factor * self.config.liquidity_weight +
            volume_factor * self.config.volume_weight +
            pressure_factor * self.config.pressure_weight +
            depth_factor * 0.05 +
            imbalance_factor * 0.05
        )
        
        # 计算新价差
        target_spread = current_spread * (1 + weighted_adjustment)
        clamped_spread = max(
            self.config.min_spread,
            min(self.config.max_spread, target_spread)
        )
        
        # 平滑调整
        smoothed_spread = (
            current_spread * (1 - self.config.adjustment_speed) +
            clamped_spread * self.config.adjustment_speed
        )
        
        # 计算置信度
        confidence = self._calculate_confidence(condition, factors)
        
        # 生成调整原因
        reason = self._generate_reason(factors, weighted_adjustment)
        
        # 更新历史
        self._update_history(market_id, smoothed_spread)
        
        self.adjustment_count += 1
        self.total_adjustments += abs(smoothed_spread - current_spread)
        
        return SpreadAdjustment(
            new_spread=round(smoothed_spread, 6),
            confidence=round(confidence, 3),
            reason=reason,
            factors={k: round(v, 4) for k, v in factors.items()}
        )
    
    def calculate_optimal_spread(
        self,
        market_id: str,
        orderbook: Dict,
        recent_trades: List[Dict],
        volatility: float = 0.0
    ) -> SpreadAdjustment:
        """
        根据订单簿和交易历史计算最优价差
        """
        # 解析订单簿
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        best_bid = float(bids[0]["price"]) if bids else 0
        best_ask = float(asks[0]["price"]) if asks else 1
        
        current_spread = best_ask - best_bid if best_bid > 0 else self.config.base_spread
        
        # 计算市场状况
        condition = MarketCondition(
            volatility=volatility,
            liquidity=sum(float(b.get("size", 0)) for b in bids) + sum(float(a.get("size", 0)) for a in asks),
            spread=current_spread,
            volume=sum(float(t.get("size", 0)) for t in recent_trades[-20:]) if recent_trades else 0,
            pressure=self._calculate_pressure_from_orderbook(bids, asks),
            depth_trend=1.0,
            imbalance=self._calculate_imbalance_from_orderbook(bids, asks)
        )
        
        return self.calculate_adjustment(market_id, condition, current_spread)
    
    def _calculate_volatility_factor(self, volatility: float) -> float:
        """
        波动性因素计算
        高波动 -> 扩大价差
        """
        if volatility > 0.01:
            return min((volatility - 0.01) * 5, 0.5)  # 最多增加50%
        if volatility < 0.005:
            return -(0.005 - volatility) * 3  # 最多减少15%
        return 0.0
    
    def _calculate_liquidity_factor(self, liquidity: float) -> float:
        """
        流动性因素计算
        低流动性 -> 扩大价差
        """
        threshold = 1000  # 1000 USDT
        if liquidity < threshold:
            return -((threshold - liquidity) / threshold) * 0.3
        return 0.0
    
    def _calculate_volume_factor(self, volume: float) -> float:
        """
        成交量因素计算
        高成交量 -> 可以缩小价差
        """
        threshold = 10000  # 10000 USDT
        if volume > threshold:
            return -min((volume - threshold) / threshold * 0.2, 0.2)
        return 0.0
    
    def _calculate_pressure_factor(self, pressure: float) -> float:
        """
        压力因素计算
        高压力（单边）-> 扩大价差
        """
        abs_pressure = abs(pressure)
        if abs_pressure > 0.5:
            return (abs_pressure - 0.5) * 0.3
        return 0.0
    
    def _calculate_depth_trend_factor(self, depth_trend: float) -> float:
        """
        深度趋势因素计算
        深度下降 -> 扩大价差
        """
        if depth_trend < 0.8:
            return (0.8 - depth_trend) * 0.2
        return 0.0
    
    def _calculate_imbalance_factor(self, imbalance: float) -> float:
        """
        订单簿失衡因素计算
        严重失衡 -> 扩大价差
        """
        abs_imbalance = abs(imbalance)
        if abs_imbalance > 0.3:
            return (abs_imbalance - 0.3) * 0.3
        return 0.0
    
    def _calculate_pressure_from_orderbook(self, bids: List, asks: List) -> float:
        """从订单簿计算买卖压力"""
        bid_volume = sum(float(b.get("size", 0)) for b in bids[:5])
        ask_volume = sum(float(a.get("size", 0)) for a in asks[:5])
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        return (bid_volume - ask_volume) / total
    
    def _calculate_imbalance_from_orderbook(self, bids: List, asks: List) -> float:
        """从订单簿计算失衡"""
        bid_volume = sum(float(b.get("size", 0)) for b in bids)
        ask_volume = sum(float(a.get("size", 0)) for a in asks)
        total = bid_volume + ask_volume
        if total == 0:
            return 0.0
        return (bid_volume - ask_volume) / total
    
    def _calculate_confidence(self, condition: MarketCondition, factors: Dict[str, float]) -> float:
        """计算调整置信度"""
        confidence = 0.5  # 基础置信度
        
        # 数据完整性加分
        if condition.volatility > 0:
            confidence += 0.1
        if condition.liquidity > 0:
            confidence += 0.1
        if condition.volume > 0:
            confidence += 0.1
        
        # 调整方向一致性加分
        adjustments = list(factors.values())
        all_positive = all(a > 0 for a in adjustments)
        all_negative = all(a < 0 for a in adjustments)
        if all_positive or all_negative:
            confidence += 0.15
        
        # 调整幅度合理性
        total_adjustment = abs(sum(adjustments))
        if 0.05 < total_adjustment < 0.3:
            confidence += 0.05
        
        return min(1.0, confidence)
    
    def _generate_reason(self, factors: Dict[str, float], total_adjustment: float) -> str:
        """生成调整原因"""
        reasons = []
        
        if abs(factors.get("volatility", 0)) > 0.05:
            reasons.append("高波动" if factors["volatility"] > 0 else "低波动")
        if abs(factors.get("liquidity", 0)) > 0.05:
            reasons.append("流动性充足" if factors["liquidity"] > 0 else "流动性不足")
        if abs(factors.get("volume", 0)) > 0.05:
            reasons.append("低成交量" if factors["volume"] > 0 else "高成交量")
        if abs(factors.get("pressure", 0)) > 0.05:
            reasons.append("买压高" if factors["pressure"] > 0 else "卖压高")
        if abs(factors.get("depth_trend", 0)) > 0.05:
            reasons.append("深度增加" if factors["depth_trend"] > 0 else "深度下降")
        if abs(factors.get("imbalance", 0)) > 0.05:
            reasons.append("订单簿失衡")
        
        if not reasons:
            return "市场状况稳定"
        
        direction = "扩大" if total_adjustment > 0 else "缩小"
        return f"{direction}价差: {', '.join(reasons)}"
    
    def _update_history(self, market_id: str, spread: float):
        """更新价差历史"""
        if market_id not in self.spread_history:
            self.spread_history[market_id] = deque(maxlen=100)
        self.spread_history[market_id].append(spread)
    
    def get_history(self, market_id: str) -> List[float]:
        """获取价差历史"""
        return list(self.spread_history.get(market_id, []))
    
    def get_spread_volatility(self, market_id: str) -> float:
        """计算价差波动性"""
        history = self.get_history(market_id)
        if len(history) < 2:
            return 0.0
        
        mean = sum(history) / len(history)
        variance = sum((v - mean) ** 2 for v in history) / len(history)
        return variance ** 0.5
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "adjustment_count": self.adjustment_count,
            "total_adjustments": round(self.total_adjustments, 6),
            "avg_adjustment": round(self.total_adjustments / max(1, self.adjustment_count), 6),
            "markets_tracked": len(self.spread_history)
        }
    
    def reset(self):
        """重置统计"""
        self.spread_history.clear()
        self.adjustment_count = 0
        self.total_adjustments = 0.0
    
    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)


# 全局单例
dynamic_spread_calculator = DynamicSpreadCalculator()

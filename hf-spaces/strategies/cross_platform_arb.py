"""
跨平台套利模块 (Cross-Platform Arbitrage)

支持多平台价差套利：
- Polymarket
- Predict.fun
- Probable
- Kalshi

功能：
- 市场匹配检测
- 价差计算
- 套利机会发现
- 执行建议
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from loguru import logger


class Platform(Enum):
    """交易平台"""
    POLYMARKET = "polymarket"
    PREDICT_FUN = "predict_fun"
    PROBABLE = "probable"
    KALSHI = "kalshi"


class ArbitrageType(Enum):
    """套利类型"""
    CROSS_PLATFORM = "cross_platform"      # 跨平台套利
    INTRA_PLATFORM = "intra_platform"      # 站内套利
    VALUE_MISMATCH = "value_mismatch"      # 价值错配
    MULTI_OUTCOME = "multi_outcome"        # 多结果套利


@dataclass
class PlatformMarket:
    """平台市场"""
    platform: Platform
    market_id: str
    question: str
    yes_price: float
    no_price: float
    yes_token_id: Optional[str] = None
    no_token_id: Optional[str] = None
    liquidity: float = 0.0
    volume_24h: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    opportunity_id: str
    arb_type: ArbitrageType
    market_a: PlatformMarket
    market_b: Optional[PlatformMarket]
    profit_pct: float
    profit_usd: float
    confidence: float
    action: str
    details: Dict
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 执行信息
    executed: bool = False
    execution_price: Optional[float] = None
    execution_time: Optional[datetime] = None


@dataclass
class CrossPlatformConfig:
    """跨平台套利配置"""
    enabled: bool = False
    min_profit_pct: float = 0.01          # 最小利润率 1%
    min_similarity: float = 0.78          # 最小相似度
    auto_execute: bool = False            # 自动执行
    require_confirm: bool = True          # 需要确认
    transfer_cost: float = 0.002          # 转账成本
    slippage_bps: float = 250.0           # 滑点
    max_position_usd: float = 500.0       # 最大仓位
    fee_bps: float = 100.0                # 手续费


class CrossPlatformArbitrage:
    """跨平台套利"""
    
    def __init__(self, config: Optional[CrossPlatformConfig] = None):
        self.config = config or CrossPlatformConfig()
        self.markets: Dict[Platform, Dict[str, PlatformMarket]] = {
            platform: {} for platform in Platform
        }
        self.opportunities: List[ArbitrageOpportunity] = []
        self.executed_trades: List[Dict] = []
        self.market_mappings: Dict[str, Dict] = {}  # 市场映射
    
    def add_market(self, market: PlatformMarket):
        """添加市场"""
        self.markets[market.platform][market.market_id] = market
    
    def update_market(self, platform: Platform, market_id: str, 
                      yes_price: float, no_price: float,
                      liquidity: float = 0, volume_24h: float = 0):
        """更新市场数据"""
        if market_id in self.markets[platform]:
            market = self.markets[platform][market_id]
            market.yes_price = yes_price
            market.no_price = no_price
            market.liquidity = liquidity
            market.volume_24h = volume_24h
            market.timestamp = datetime.now()
    
    def find_cross_platform_opportunities(self) -> List[ArbitrageOpportunity]:
        """发现跨平台套利机会"""
        opportunities = []
        
        # 遍历所有平台组合
        platforms = list(Platform)
        for i, platform_a in enumerate(platforms):
            for platform_b in platforms[i+1:]:
                opps = self._find_opportunities_between_platforms(platform_a, platform_b)
                opportunities.extend(opps)
        
        # 按利润排序
        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        
        self.opportunities = opportunities
        return opportunities
    
    def find_intra_platform_opportunities(self, platform: Platform) -> List[ArbitrageOpportunity]:
        """发现站内套利机会 (Yes + No != 1)"""
        opportunities = []
        
        for market_id, market in self.markets[platform].items():
            total = market.yes_price + market.no_price
            
            # 如果 Yes + No != 1，存在套利机会
            if total < 0.99:
                # 低估，可以买入两边
                profit_pct = (1 - total) / total
                if profit_pct >= self.config.min_profit_pct:
                    opp = ArbitrageOpportunity(
                        opportunity_id=f"intra_{platform.value}_{market_id}",
                        arb_type=ArbitrageType.INTRA_PLATFORM,
                        market_a=market,
                        market_b=None,
                        profit_pct=profit_pct,
                        profit_usd=self.config.max_position_usd * profit_pct,
                        confidence=0.9,
                        action="BUY_BOTH",
                        details={
                            "yes_price": market.yes_price,
                            "no_price": market.no_price,
                            "total": total,
                            "deviation": 1 - total
                        }
                    )
                    opportunities.append(opp)
            
            elif total > 1.01:
                # 高估，但需要已有持仓才能做空
                profit_pct = (total - 1) / total
                if profit_pct >= self.config.min_profit_pct:
                    opp = ArbitrageOpportunity(
                        opportunity_id=f"intra_{platform.value}_{market_id}",
                        arb_type=ArbitrageType.INTRA_PLATFORM,
                        market_a=market,
                        market_b=None,
                        profit_pct=profit_pct,
                        profit_usd=self.config.max_position_usd * profit_pct,
                        confidence=0.7,
                        action="SELL_OVERVALUED",
                        details={
                            "yes_price": market.yes_price,
                            "no_price": market.no_price,
                            "total": total,
                            "deviation": total - 1
                        }
                    )
                    opportunities.append(opp)
        
        return opportunities
    
    def _find_opportunities_between_platforms(
        self, 
        platform_a: Platform, 
        platform_b: Platform
    ) -> List[ArbitrageOpportunity]:
        """在两个平台之间寻找套利机会"""
        opportunities = []
        
        markets_a = self.markets[platform_a]
        markets_b = self.markets[platform_b]
        
        for market_a in markets_a.values():
            for market_b in markets_b.values():
                # 检查相似度
                similarity = self._calculate_similarity(market_a.question, market_b.question)
                
                if similarity < self.config.min_similarity:
                    continue
                
                # 计算价差套利机会
                opp = self._calculate_arbitrage(market_a, market_b, similarity)
                if opp:
                    opportunities.append(opp)
        
        return opportunities
    
    def _calculate_arbitrage(
        self, 
        market_a: PlatformMarket, 
        market_b: PlatformMarket,
        similarity: float
    ) -> Optional[ArbitrageOpportunity]:
        """计算套利机会"""
        # 检查 YES 价差
        yes_diff = market_a.yes_price - market_b.yes_price
        
        # 扣除成本后的利润
        fee_cost = self.config.fee_bps / 10000
        slippage_cost = self.config.slippage_bps / 10000
        transfer_cost = self.config.transfer_cost
        total_cost = fee_cost * 2 + slippage_cost * 2 + transfer_cost
        
        # 如果 A 平台 YES 价格低于 B 平台
        if abs(yes_diff) > total_cost + self.config.min_profit_pct:
            profit_pct = abs(yes_diff) - total_cost
            
            if yes_diff < 0:
                # A 便宜，在 A 买 YES，在 B 卖 YES
                action = f"BUY_YES_{market_a.platform.value}_SELL_YES_{market_b.platform.value}"
            else:
                # B 便宜，在 B 买 YES，在 A 卖 YES
                action = f"BUY_YES_{market_b.platform.value}_SELL_YES_{market_a.platform.value}"
            
            return ArbitrageOpportunity(
                opportunity_id=f"cross_{market_a.platform.value}_{market_b.platform.value}_{market_a.market_id}",
                arb_type=ArbitrageType.CROSS_PLATFORM,
                market_a=market_a,
                market_b=market_b,
                profit_pct=profit_pct,
                profit_usd=self.config.max_position_usd * profit_pct,
                confidence=similarity,
                action=action,
                details={
                    "yes_price_a": market_a.yes_price,
                    "yes_price_b": market_b.yes_price,
                    "price_diff": yes_diff,
                    "total_cost": total_cost,
                    "similarity": similarity
                }
            )
        
        return None
    
    def _calculate_similarity(self, question_a: str, question_b: str) -> float:
        """计算问题相似度"""
        # 标准化问题
        def normalize(q: str) -> str:
            q = q.lower()
            # 移除常见停用词
            q = re.sub(r'\b(yes|no|true|false|will|be|is|are|the|a|an)\b', '', q)
            q = re.sub(r'[^a-z0-9\u4e00-\u9fa5]+', ' ', q)
            return q.strip()
        
        s1 = normalize(question_a)
        s2 = normalize(question_b)
        
        if not s1 or not s2:
            return 0.0
        
        # Jaccard 相似度
        words1 = set(s1.split())
        words2 = set(s2.split())
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union) if union else 0.0
    
    def execute_arbitrage(self, opportunity: ArbitrageOpportunity, 
                          size_usd: Optional[float] = None) -> Dict:
        """执行套利"""
        if not self.config.auto_execute and self.config.require_confirm:
            return {
                "success": False,
                "reason": "需要手动确认",
                "opportunity": opportunity
            }
        
        size = size_usd or self.config.max_position_usd
        
        # 模拟执行
        execution = {
            "opportunity_id": opportunity.opportunity_id,
            "action": opportunity.action,
            "size_usd": size,
            "expected_profit": size * opportunity.profit_pct,
            "timestamp": datetime.now().isoformat(),
            "success": True,
            "simulation": True
        }
        
        opportunity.executed = True
        opportunity.execution_time = datetime.now()
        
        self.executed_trades.append(execution)
        
        logger.info(f"✅ 套利执行: {opportunity.action}, 预期利润: ${execution['expected_profit']:.2f}")
        
        return execution
    
    def get_top_opportunities(self, limit: int = 10) -> List[ArbitrageOpportunity]:
        """获取最佳套利机会"""
        return sorted(self.opportunities, key=lambda x: x.profit_pct, reverse=True)[:limit]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        total_profit = sum(
            t.get("expected_profit", 0) for t in self.executed_trades if t.get("success")
        )
        
        return {
            "total_opportunities": len(self.opportunities),
            "opportunities_by_type": {
                arb_type.value: sum(1 for o in self.opportunities if o.arb_type == arb_type)
                for arb_type in ArbitrageType
            },
            "executed_trades": len(self.executed_trades),
            "total_profit": round(total_profit, 2),
            "markets_tracked": {
                platform.value: len(markets) 
                for platform, markets in self.markets.items()
            }
        }
    
    def add_market_mapping(self, polymarket_id: str, predict_id: str, 
                           probable_id: Optional[str] = None):
        """添加市场映射（手动配置相同事件）"""
        self.market_mappings[polymarket_id] = {
            "polymarket": polymarket_id,
            "predict_fun": predict_id,
            "probable": probable_id
        }
    
    def get_mapped_markets(self, market_id: str) -> Optional[Dict]:
        """获取映射的市场"""
        return self.market_mappings.get(market_id)
    
    def clear_opportunities(self):
        """清空机会列表"""
        self.opportunities.clear()
    
    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)


# 全局单例
cross_platform_arbitrage = CrossPlatformArbitrage()

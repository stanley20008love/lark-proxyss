"""
统一做市商策略 (Unified Market Maker Strategy)

整合了所有策略的优点：
- 两阶段循环对冲的基础逻辑
- 颗粒度对冲的异步对冲逻辑
- 双轨并行操作的积分最大化

核心特性：
1. 异步对冲：成交一点 → 立即对冲一点（不撤单）
2. 双轨并行：同时在买入端和卖出端赚积分
3. 恒定价值：YES + NO = 1，持有 1:1 时风险为零
4. 积分最大化：不间断挂单，持续赚取积分
"""
from typing import Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from loguru import logger


class UnifiedState(Enum):
    """做市商状态"""
    EMPTY = "EMPTY"                 # 空仓
    HEDGED = "HEDGED"               # 已对冲（1:1）
    DUAL_TRACK = "DUAL_TRACK"       # 双轨并行（最优状态）


class ActionType(Enum):
    """操作类型"""
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    SELL_YES = "SELL_YES"
    SELL_NO = "SELL_NO"
    PLACE_ORDERS = "PLACE_ORDERS"
    NONE = "NONE"


class Priority(Enum):
    """优先级"""
    URGENT = "URGENT"
    NORMAL = "NORMAL"


@dataclass
class UnifiedAction:
    """统一操作"""
    needs_action: bool
    action_type: ActionType
    shares: float
    reason: str
    priority: Priority


@dataclass
class UnifiedMarketMakerConfig:
    """统一做市商配置"""
    enabled: bool = False
    tolerance: float = 0.05               # 对冲偏差容忍度（5%）
    min_hedge_size: float = 10.0          # 最小对冲数量
    max_hedge_size: float = 500.0         # 最大对冲数量
    buy_spread_bps: float = 150.0         # Buy 单价差（基点）
    sell_spread_bps: float = 150.0        # Sell 单价差（基点）
    hedge_slippage_bps: float = 250.0     # 对冲滑点（基点）
    async_hedging: bool = True            # 启用异步对冲（不撤单）
    dual_track_mode: bool = True          # 启用双轨并行模式
    dynamic_offset_mode: bool = True      # 启用动态偏移模式
    buy_offset_bps: float = 100.0         # Buy 单偏移量（基点）
    sell_offset_bps: float = 100.0        # Sell 单偏移量（基点）


@dataclass
class Position:
    """持仓"""
    yes_amount: float = 0.0
    no_amount: float = 0.0
    avg_yes_price: float = 0.0
    avg_no_price: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderbookLevel:
    """订单簿层级"""
    price: float
    size: float


@dataclass
class Orderbook:
    """订单簿"""
    bids: List[OrderbookLevel] = field(default_factory=list)
    asks: List[OrderbookLevel] = field(default_factory=list)
    best_bid: float = 0.0
    best_ask: float = 0.0


class UnifiedMarketMakerStrategy:
    """统一做市商策略"""
    
    def __init__(self, config: Optional[UnifiedMarketMakerConfig] = None):
        self.config = config or UnifiedMarketMakerConfig()
        self.positions: Dict[str, Position] = {}
        self.active_orders: Dict[str, List[Dict]] = {}
        self.stats = {
            "orders_placed": 0,
            "orders_filled": 0,
            "hedges_executed": 0,
            "points_earned": 0.0
        }
    
    def analyze(self, market_id: str, position: Position, 
                yes_price: float, no_price: float) -> Dict:
        """
        分析当前状态并给出操作建议
        """
        yes_shares = position.yes_amount
        no_shares = position.no_amount
        total_shares = yes_shares + no_shares
        
        # 计算偏差
        avg_shares = total_shares / 2
        deviation = abs(yes_shares - no_shares) / avg_shares if avg_shares > 0 else 0
        is_balanced = deviation <= self.config.tolerance
        
        # 判断状态
        state: UnifiedState
        should_place_buy_orders = False
        should_place_sell_orders = False
        
        if total_shares == 0:
            state = UnifiedState.EMPTY
            should_place_buy_orders = True
        elif is_balanced and total_shares >= self.config.min_hedge_size:
            # 已对冲，启用双轨并行
            state = UnifiedState.DUAL_TRACK
            should_place_buy_orders = True
            should_place_sell_orders = True
        elif not is_balanced:
            # 不平衡，需要继续对冲
            state = UnifiedState.HEDGED
            should_place_buy_orders = True
            should_place_sell_orders = yes_shares > 0 or no_shares > 0
        else:
            state = UnifiedState.EMPTY
            should_place_buy_orders = True
        
        # 计算订单大小
        base_order_size = max(10, int(self.config.min_hedge_size))
        buy_order_size = base_order_size if should_place_buy_orders else 0
        sell_order_size = min(base_order_size, int(total_shares / 2)) if should_place_sell_orders else 0
        
        return {
            "state": state,
            "should_place_buy_orders": should_place_buy_orders,
            "should_place_sell_orders": should_place_sell_orders,
            "buy_order_size": buy_order_size,
            "sell_order_size": sell_order_size,
            "deviation": deviation,
            "is_balanced": is_balanced
        }
    
    def handle_order_fill(
        self,
        market_id: str,
        side: Literal["BUY", "SELL"],
        token: Literal["YES", "NO"],
        filled_shares: float,
        current_yes_shares: float,
        current_no_shares: float
    ) -> UnifiedAction:
        """
        处理订单成交（异步对冲逻辑）
        """
        logger.info(f"📝 订单成交: {token} {side} {filled_shares} 股")
        logger.info(f"   当前持仓: {current_yes_shares} YES + {current_no_shares} NO")
        
        # 计算成交后的持仓
        new_yes_shares = current_yes_shares
        new_no_shares = current_no_shares
        
        if side == "BUY":
            if token == "YES":
                new_yes_shares += filled_shares
            else:
                new_no_shares += filled_shares
        else:
            if token == "YES":
                new_yes_shares -= filled_shares
            else:
                new_no_shares -= filled_shares
        
        logger.info(f"   成交后: {new_yes_shares} YES + {new_no_shares} NO")
        
        # 计算偏差
        total_shares = new_yes_shares + new_no_shares
        avg_shares = total_shares / 2
        deviation = abs(new_yes_shares - new_no_shares) / avg_shares if avg_shares > 0 else 0
        
        logger.info(f"   偏差: {deviation:.2%} (容忍度: {self.config.tolerance:.2%})")
        
        # 如果偏差超过容忍度，执行异步对冲
        if deviation > self.config.tolerance and total_shares >= self.config.min_hedge_size:
            if new_yes_shares > new_no_shares:
                # YES 过多，需要买入 NO
                excess_yes = new_yes_shares - new_no_shares
                hedge_shares = min(excess_yes, self.config.max_hedge_size)
                
                logger.info(f"🔄 异步对冲: YES 过多，买入 {hedge_shares} NO 恢复平衡")
                
                self.stats["hedges_executed"] += 1
                return UnifiedAction(
                    needs_action=True,
                    action_type=ActionType.BUY_NO,
                    shares=hedge_shares,
                    reason=f"异步对冲：{token} 被成交 {filled_shares}，买入 {hedge_shares} NO 恢复平衡",
                    priority=Priority.URGENT
                )
            else:
                # NO 过多，需要买入 YES
                excess_no = new_no_shares - new_yes_shares
                hedge_shares = min(excess_no, self.config.max_hedge_size)
                
                logger.info(f"🔄 异步对冲: NO 过多，买入 {hedge_shares} YES 恢复平衡")
                
                self.stats["hedges_executed"] += 1
                return UnifiedAction(
                    needs_action=True,
                    action_type=ActionType.BUY_YES,
                    shares=hedge_shares,
                    reason=f"异步对冲：{token} 被成交 {filled_shares}，买入 {hedge_shares} YES 恢复平衡",
                    priority=Priority.URGENT
                )
        
        return UnifiedAction(
            needs_action=False,
            action_type=ActionType.NONE,
            shares=0,
            reason="持仓平衡，无需对冲",
            priority=Priority.NORMAL
        )
    
    def suggest_order_prices(
        self,
        yes_price: float,
        no_price: float,
        yes_orderbook: Optional[Orderbook] = None,
        no_orderbook: Optional[Orderbook] = None
    ) -> Dict:
        """
        建议挂单价格（第二档动态挂单策略）
        """
        if self.config.dynamic_offset_mode:
            # 动态偏移模式：根据第一档价格计算
            buy_offset = self.config.buy_offset_bps / 10000  # 默认 1%
            sell_offset = self.config.sell_offset_bps / 10000  # 默认 1%
            
            # YES: 根据第一档价格偏移
            yes_best_bid = yes_orderbook.best_bid if yes_orderbook else yes_price
            yes_best_ask = yes_orderbook.best_ask if yes_orderbook else yes_price * 1.01
            
            yes_bid = max(0.01, yes_best_bid * (1 - buy_offset))   # 低于第一档买价
            yes_ask = max(0.01, yes_best_ask * (1 + sell_offset))  # 高于第一档卖价
            
            # NO: 根据第一档价格偏移
            no_best_bid = no_orderbook.best_bid if no_orderbook else no_price
            no_best_ask = no_orderbook.best_ask if no_orderbook else no_price * 1.01
            
            no_bid = max(0.01, no_best_bid * (1 - buy_offset))
            no_ask = max(0.01, no_best_ask * (1 + sell_offset))
            
            source = "DYNAMIC_OFFSET"
        else:
            # 固定价差模式
            buy_spread = self.config.buy_spread_bps / 10000
            sell_spread = self.config.sell_spread_bps / 10000
            
            yes_bid = max(0.01, yes_price * (1 - buy_spread))
            yes_ask = min(0.99, yes_price * (1 + sell_spread))
            no_bid = max(0.01, no_price * (1 - buy_spread))
            no_ask = min(0.99, no_price * (1 + sell_spread))
            
            source = "FIXED_SPREAD"
        
        return {
            "yes_bid": round(yes_bid, 4),
            "yes_ask": round(min(0.99, yes_ask), 4),
            "no_bid": round(no_bid, 4),
            "no_ask": round(min(0.99, no_ask), 4),
            "source": source
        }
    
    def get_position_for_market(self, market_id: str) -> Position:
        """获取市场持仓"""
        return self.positions.get(market_id, Position())
    
    def update_position(self, market_id: str, yes_amount: float, no_amount: float,
                       avg_yes_price: float = 0, avg_no_price: float = 0):
        """更新持仓"""
        if market_id not in self.positions:
            self.positions[market_id] = Position()
        
        self.positions[market_id].yes_amount = yes_amount
        self.positions[market_id].no_amount = no_amount
        self.positions[market_id].avg_yes_price = avg_yes_price
        self.positions[market_id].avg_no_price = avg_no_price
        self.positions[market_id].timestamp = datetime.now()
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            "active_markets": len(self.positions),
            "total_positions": sum(p.yes_amount + p.no_amount for p in self.positions.values())
        }
    
    def update_config(self, **kwargs):
        """更新配置"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.config.enabled


# 全局单例
unified_market_maker = UnifiedMarketMakerStrategy()

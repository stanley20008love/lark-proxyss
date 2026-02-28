"""
Execution Strategies - 执行策略

两种主要策略:
1. 做市商策略 (Market Maker): 在买卖两侧同时挂单，赚取价差
2. 吃单策略 (Taker): 等待价格偏差足够大时出手

关键考虑:
- Polymarket 的 Taker Delay (~250ms)
- 手续费和价差
- 网络中断和"幽灵成交"处理
"""
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging
import math

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    MARKET_MAKER = "market_maker"
    TAKER = "taker"
    HYBRID = "hybrid"


class OrderSide(Enum):
    BUY_YES = "buy_yes"
    BUY_NO = "buy_no"
    SELL_YES = "sell_yes"
    SELL_NO = "sell_no"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Order:
    """订单"""
    order_id: str
    market_id: str
    side: OrderSide
    price: float
    size: float
    status: OrderStatus = OrderStatus.PENDING
    created_at: float = field(default_factory=time.time)
    filled_at: Optional[float] = None
    filled_price: Optional[float] = None
    tx_hash: Optional[str] = None


@dataclass
class ExecutionConfig:
    """执行配置"""
    # 通用配置
    strategy_type: StrategyType = StrategyType.TAKER
    max_position_size: float = 100.0
    min_edge: float = 0.02  # 最小边际 2%

    # Maker 配置
    maker_spread_bps: float = 150.0  # 1.5% 价差
    maker_post_only: bool = True
    maker_refresh_interval: float = 5.0

    # Taker 配置
    taker_slippage_bps: float = 50.0  # 0.5% 滑点容忍
    taker_timeout_ms: float = 500.0  # 500ms 超时

    # 风控配置
    max_daily_trades: int = 50
    max_daily_loss: float = 100.0
    circuit_breaker_threshold: float = 0.10
    cooldown_after_trade: float = 10.0  # 交易后冷却时间


@dataclass
class MarketState:
    """市场状态"""
    market_id: str
    question: str
    yes_price: float
    no_price: float
    theoretical_yes: float
    theoretical_no: float
    edge: float
    bid: float
    ask: float
    liquidity: float
    timestamp: float


class ExecutionEngine:
    """
    执行引擎

    根据 StrategyType 选择不同的执行策略
    """

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Dict] = {}
        self.daily_stats = {
            "trades": 0,
            "pnl": 0.0,
            "wins": 0,
            "losses": 0
        }
        self.last_trade_time: float = 0
        self.circuit_breaker_active: bool = False

        self.on_order_filled: Optional[Callable] = None
        self.on_position_update: Optional[Callable] = None

    async def execute(
        self,
        market_state: MarketState,
        pricing_result: Dict
    ) -> Optional[Order]:
        """
        执行交易

        根据配置的策略类型选择执行方式
        """
        # 检查熔断
        if self.circuit_breaker_active:
            logger.warning("Circuit breaker active, skipping execution")
            return None

        # 检查冷却时间
        if time.time() - self.last_trade_time < self.config.cooldown_after_trade:
            logger.debug("In cooldown period")
            return None

        # 检查日交易限制
        if self.daily_stats["trades"] >= self.config.max_daily_trades:
            logger.warning("Daily trade limit reached")
            return None

        # 根据策略类型执行
        if self.config.strategy_type == StrategyType.MARKET_MAKER:
            return await self._execute_maker(market_state, pricing_result)
        elif self.config.strategy_type == StrategyType.TAKER:
            return await self._execute_taker(market_state, pricing_result)
        else:  # HYBRID
            return await self._execute_hybrid(market_state, pricing_result)

    async def _execute_maker(
        self,
        market_state: MarketState,
        pricing_result: Dict
    ) -> Optional[Order]:
        """
        做市商策略

        在买卖两侧同时挂单，赚取价差
        优势: 如果模型准确，可以以低于 $1 的总成本同时持有"涨"和"跌"头寸
        """
        theo_yes = pricing_result.get("theoretical_price", 0.5)
        edge = pricing_result.get("edge", 0)

        # 计算挂单价格
        spread = self.config.maker_spread_bps / 10000
        bid_price = theo_yes - spread / 2
        ask_price = theo_yes + spread / 2

        # 确保价格在合理范围内
        bid_price = max(0.01, min(0.99, bid_price))
        ask_price = max(0.01, min(0.99, ask_price))

        # 创建双向挂单
        orders = []

        # 检查是否值得挂单
        if market_state.bid < bid_price:
            # 可以在更低价买入
            buy_order = Order(
                order_id=f"buy_{market_state.market_id}_{int(time.time()*1000)}",
                market_id=market_state.market_id,
                side=OrderSide.BUY_YES,
                price=bid_price,
                size=self.config.max_position_size / bid_price
            )
            orders.append(buy_order)

        if market_state.ask > ask_price:
            # 可以在更高价卖出
            sell_order = Order(
                order_id=f"sell_{market_state.market_id}_{int(time.time()*1000)}",
                market_id=market_state.market_id,
                side=OrderSide.SELL_YES,
                price=ask_price,
                size=self.config.max_position_size / ask_price
            )
            orders.append(sell_order)

        if orders:
            logger.info(f"Maker: Placing {len(orders)} orders for {market_state.market_id}")
            for order in orders:
                self.orders[order.order_id] = order

        return orders[0] if orders else None

    async def _execute_taker(
        self,
        market_state: MarketState,
        pricing_result: Dict
    ) -> Optional[Order]:
        """
        吃单策略

        待在场外，当价格偏差足够大时才出手
        优势: 代码架构简单，不需要实时挂单，受网络中断影响较小
        """
        theo_yes = pricing_result.get("theoretical_price", 0.5)
        edge = pricing_result.get("edge", 0)
        market_yes = market_state.yes_price

        # 计算需要覆盖的成本
        # 手续费 + 滑点
        total_cost = 0.02  # 2% 总成本

        # 检查边际是否足够
        if abs(edge) < max(self.config.min_edge, total_cost):
            logger.debug(f"Edge {edge:.2%} too small, skipping")
            return None

        # 决定方向
        if edge > 0:
            # 理论价格 > 市场价格，买入 YES
            side = OrderSide.BUY_YES
            price = min(market_state.ask, theo_yes - total_cost/2)
        else:
            # 理论价格 < 市场价格，买入 NO (或卖 YES)
            side = OrderSide.BUY_NO
            price = min(1 - market_state.bid, 1 - theo_yes - total_cost/2)

        # 检查滑点
        slippage = self.config.taker_slippage_bps / 10000
        if side == OrderSide.BUY_YES:
            max_price = market_state.ask * (1 + slippage)
            if price > max_price:
                logger.warning(f"Price {price:.4f} exceeds max with slippage {max_price:.4f}")
                return None

        # 创建订单
        order = Order(
            order_id=f"taker_{market_state.market_id}_{int(time.time()*1000)}",
            market_id=market_state.market_id,
            side=side,
            price=price,
            size=self.config.max_position_size / price
        )

        self.orders[order.order_id] = order
        self.last_trade_time = time.time()
        self.daily_stats["trades"] += 1

        logger.info(f"Taker: {side.value} {order.size:.2f} @ {price:.4f}")

        return order

    async def _execute_hybrid(
        self,
        market_state: MarketState,
        pricing_result: Dict
    ) -> Optional[Order]:
        """
        混合策略

        根据市场条件自动切换 Maker 和 Taker
        """
        edge = abs(pricing_result.get("edge", 0))
        liquidity = market_state.liquidity

        # 高边际 + 低流动性 -> Taker (快速捕获机会)
        if edge > 0.05 and liquidity < 50000:
            logger.info("Hybrid: Switching to Taker (high edge, low liquidity)")
            return await self._execute_taker(market_state, pricing_result)

        # 低边际 + 高流动性 -> Maker (赚取价差)
        elif edge < 0.03 and liquidity > 100000:
            logger.info("Hybrid: Switching to Maker (low edge, high liquidity)")
            return await self._execute_maker(market_state, pricing_result)

        # 中等情况，使用 Taker
        else:
            return await self._execute_taker(market_state, pricing_result)

    async def cancel_order(self, order_id: str) -> bool:
        """取消订单"""
        if order_id in self.orders:
            self.orders[order_id].status = OrderStatus.CANCELLED
            logger.info(f"Cancelled order {order_id}")
            return True
        return False

    async def cancel_all_orders(self, market_id: str = None):
        """取消所有订单"""
        for order_id, order in self.orders.items():
            if market_id is None or order.market_id == market_id:
                order.status = OrderStatus.CANCELLED

    def on_fill(self, order_id: str, filled_price: float, filled_size: float):
        """处理成交"""
        if order_id not in self.orders:
            return

        order = self.orders[order_id]
        order.status = OrderStatus.FILLED
        order.filled_at = time.time()
        order.filled_price = filled_price

        # 更新持仓
        market_id = order.market_id
        if market_id not in self.positions:
            self.positions[market_id] = {
                "yes_size": 0,
                "no_size": 0,
                "avg_yes_price": 0,
                "avg_no_price": 0
            }

        pos = self.positions[market_id]

        if order.side in [OrderSide.BUY_YES, OrderSide.SELL_YES]:
            if order.side == OrderSide.BUY_YES:
                new_size = pos["yes_size"] + filled_size
                pos["avg_yes_price"] = (
                    (pos["avg_yes_price"] * pos["yes_size"] + filled_price * filled_size)
                    / new_size if new_size > 0 else 0
                )
                pos["yes_size"] = new_size
            else:
                pos["yes_size"] -= filled_size

        # 更新统计
        self.last_trade_time = time.time()

        if self.on_order_filled:
            self.on_order_filled(order, filled_price, filled_size)

        logger.info(f"Order filled: {order_id} @ {filled_price:.4f}")

    def update_pnl(self, market_id: str, current_yes_price: float):
        """更新 PnL"""
        if market_id not in self.positions:
            return

        pos = self.positions[market_id]
        pnl = 0

        if pos["yes_size"] > 0:
            pnl += pos["yes_size"] * (current_yes_price - pos["avg_yes_price"])

        self.daily_stats["pnl"] = pnl

        # 检查熔断
        if pnl < -self.config.max_daily_loss:
            self.circuit_breaker_active = True
            logger.critical(f"Circuit breaker triggered: PnL {pnl:.2f}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "strategy": self.config.strategy_type.value,
            "total_orders": len(self.orders),
            "active_orders": len([o for o in self.orders.values() if o.status == OrderStatus.PENDING]),
            "filled_orders": len([o for o in self.orders.values() if o.status == OrderStatus.FILLED]),
            "positions": len(self.positions),
            "daily_trades": self.daily_stats["trades"],
            "daily_pnl": self.daily_stats["pnl"],
            "circuit_breaker": self.circuit_breaker_active
        }


class PolymarketTakerDelayHandler:
    """
    Polymarket Taker Delay 处理器

    Polymarket 的 Taker Delay 约 250ms
    需要相应调整策略
    """

    def __init__(self, avg_delay_ms: float = 250):
        self.avg_delay_ms = avg_delay_ms
        self.delay_samples: List[float] = []
        self.max_samples = 100

    def record_delay(self, actual_delay_ms: float):
        """记录实际延迟"""
        self.delay_samples.append(actual_delay_ms)
        if len(self.delay_samples) > self.max_samples:
            self.delay_samples = self.delay_samples[-self.max_samples:]

    def get_adjusted_edge(self, raw_edge: float, volatility: float) -> float:
        """
        计算延迟调整后的边际

        在延迟期间，价格可能变化
        """
        # 估算延迟期间的价格变化
        # 使用简单的波动率模型
        delay_seconds = self.avg_delay_ms / 1000
        expected_price_move = volatility * math.sqrt(delay_seconds / (365 * 24 * 3600))

        # 调整边际
        adjusted_edge = raw_edge - expected_price_move

        return adjusted_edge

    def should_execute(
        self,
        edge: float,
        volatility: float,
        min_edge: float = 0.02
    ) -> bool:
        """
        判断是否应该执行

        考虑延迟风险后的决策
        """
        adjusted_edge = self.get_adjusted_edge(edge, volatility)

        if adjusted_edge < min_edge:
            logger.debug(
                f"Adjusted edge {adjusted_edge:.2%} < min edge {min_edge:.2%}, "
                f"raw edge {edge:.2%}, delay adjustment {edge - adjusted_edge:.2%}"
            )
            return False

        return True


class GhostFillHandler:
    """
    幽灵成交处理器

    处理高延迟、网络中断导致的"幽灵成交"问题
    """

    def __init__(self):
        self.pending_confirms: Dict[str, float] = {}
        self.confirmed_fills: Dict[str, bool] = {}
        self.timeout_seconds = 30

    def add_pending(self, order_id: str):
        """添加待确认订单"""
        self.pending_confirms[order_id] = time.time()

    def confirm_fill(self, order_id: str, filled: bool):
        """确认成交状态"""
        if order_id in self.pending_confirms:
            del self.pending_confirms[order_id]
        self.confirmed_fills[order_id] = filled

    def check_timeouts(self) -> List[str]:
        """检查超时的待确认订单"""
        now = time.time()
        timed_out = []

        for order_id, timestamp in list(self.pending_confirms.items()):
            if now - timestamp > self.timeout_seconds:
                timed_out.append(order_id)
                del self.pending_confirms[order_id]

        return timed_out

    def is_ghost_fill(self, order_id: str) -> Optional[bool]:
        """
        检查是否是幽灵成交

        Returns:
            True = 幽灵成交 (假成交)
            False = 真实成交
            None = 未确认
        """
        if order_id in self.confirmed_fills:
            return not self.confirmed_fills[order_id]
        return None


# 便捷函数
def create_taker_engine(
    min_edge: float = 0.02,
    max_position: float = 100.0,
    max_daily_trades: int = 50
) -> ExecutionEngine:
    """创建 Taker 执行引擎"""
    config = ExecutionConfig(
        strategy_type=StrategyType.TAKER,
        min_edge=min_edge,
        max_position_size=max_position,
        max_daily_trades=max_daily_trades
    )
    return ExecutionEngine(config)


def create_maker_engine(
    spread_bps: float = 150.0,
    max_position: float = 100.0
) -> ExecutionEngine:
    """创建 Maker 执行引擎"""
    config = ExecutionConfig(
        strategy_type=StrategyType.MARKET_MAKER,
        maker_spread_bps=spread_bps,
        max_position_size=max_position
    )
    return ExecutionEngine(config)


if __name__ == "__main__":
    # 测试示例
    engine = create_taker_engine(min_edge=0.015)

    # 模拟市场状态
    market = MarketState(
        market_id="btc_100k",
        question="BTC > $100k?",
        yes_price=0.35,
        no_price=0.65,
        theoretical_yes=0.42,
        theoretical_no=0.58,
        edge=0.07,  # 7% 边际
        bid=0.34,
        ask=0.36,
        liquidity=150000,
        timestamp=time.time()
    )

    pricing = {
        "theoretical_price": 0.42,
        "edge": 0.07,
        "signal": "BUY_YES"
    }

    # 执行
    async def test():
        order = await engine.execute(market, pricing)
        if order:
            print(f"Order created: {order.order_id}")
            print(f"Side: {order.side.value}")
            print(f"Price: {order.price:.4f}")
            print(f"Size: {order.size:.2f}")
        print(f"Stats: {engine.get_stats()}")

    asyncio.run(test())

"""
Polymarket 吃单策略 (Taker Strategy)

基于定价模型的吃单策略：
- 等待价格偏离足够大时才出手
- 比 Maker 策略简单，适合新手
- 不需要实时挂单，受网络中断影响小
"""
import asyncio
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from loguru import logger

from pricing.black_scholes import BinaryOptionsPricer, PricingResult, OptionType
from pricing.binance_data import MultiSymbolDataFeed, PriceTick


class SignalType(Enum):
    BUY_YES = "BUY_YES"
    BUY_NO = "BUY_NO"
    SELL_YES = "SELL_YES"
    SELL_NO = "SELL_NO"
    HOLD = "HOLD"


class SignalStrength(Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


@dataclass
class TradingSignal:
    """交易信号"""
    market_id: str
    signal_type: SignalType
    strength: SignalStrength
    theoretical_price: float
    market_price: float
    edge: float
    confidence: float
    timestamp: float
    reason: str
    position_size: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class MarketConfig:
    """市场配置"""
    market_id: str
    symbol: str           # 如 "BTC"
    target_price: float   # 目标价格 (行权价)
    expiry_minutes: int   # 到期时间 (分钟)
    market_type: str = "UP_DOWN"  # 涨跌市场


@dataclass
class TakerConfig:
    """吃单策略配置"""
    min_edge: float = 0.015         # 最小优势阈值 (1.5%)
    min_confidence: float = 0.5      # 最小置信度
    max_position_size: float = 100.0 # 最大仓位
    fee_rate: float = 0.02           # 手续费率
    slippage_rate: float = 0.005     # 滑点率
    cooldown_seconds: float = 30.0   # 交易冷却时间
    expiry_buffer_seconds: float = 60.0  # 到期缓冲 (不交易)
    volatility_threshold: float = 0.8  # 高波动阈值


class TakerStrategy:
    """
    吃单策略

    核心逻辑：
    1. 从 Binance 获取实时价格
    2. 使用 BS 模型计算理论价格
    3. 比较市场价格，寻找定价偏差
    4. 当偏差足够大时发出交易信号

    优势：
    - 初始代码架构简单
    - 不需要实时挂单
    - 受网络中断影响较小
    - 适合新手切入
    """

    def __init__(self, config: TakerConfig = None):
        self.config = config or TakerConfig()
        self.pricer = BinaryOptionsPricer()
        self.data_feed: Optional[MultiSymbolDataFeed] = None

        # 市场配置
        self.markets: Dict[str, MarketConfig] = {}
        self.market_prices: Dict[str, float] = {}  # Polymarket 市场价格

        # 信号历史
        self.signals: List[TradingSignal] = []
        self.last_trade_time: Dict[str, float] = {}

        # 回调
        self.on_signal: Optional[Callable] = None

        # 统计
        self.stats = {
            "signals_generated": 0,
            "signals_executed": 0,
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0
        }

    def add_market(self, market: MarketConfig):
        """添加监控的市场"""
        self.markets[market.market_id] = market
        logger.info(f"📊 添加市场: {market.market_id} ({market.symbol})")

    def update_market_price(self, market_id: str, yes_price: float):
        """
        更新 Polymarket 市场价格

        这需要从 Polymarket API 或 WebSocket 获取
        """
        self.market_prices[market_id] = yes_price

    async def start(self, symbols: List[str] = None):
        """
        启动策略

        Args:
            symbols: 监控的币种，如 ["BTCUSDT", "ETHUSDT"]
        """
        # 获取需要的币种
        if symbols is None:
            symbols = list(set(m.symbol + "USDT" for m in self.markets.values()))

        # 启动数据源
        self.data_feed = MultiSymbolDataFeed(symbols, use_futures=True)
        self.data_feed.add_price_callback(self._on_price_update)
        await self.data_feed.start()

        logger.info(f"🚀 吃单策略启动: {symbols}")

    async def stop(self):
        """停止策略"""
        if self.data_feed:
            await self.data_feed.stop()

    async def _on_price_update(self, tick: PriceTick):
        """价格更新回调"""
        symbol = tick.symbol.replace("USDT", "")  # 如 "BTC"

        # 找到相关的市场
        for market_id, market in self.markets.items():
            if market.symbol == symbol:
                await self._analyze_market(market, tick.price)

    async def _analyze_market(self, market: MarketConfig, current_price: float):
        """分析市场并生成信号"""
        market_id = market.market_id

        # 检查冷却时间
        last_trade = self.last_trade_time.get(market_id, 0)
        if time.time() - last_trade < self.config.cooldown_seconds:
            return

        # 检查市场价格是否存在
        if market_id not in self.market_prices:
            return

        market_yes_price = self.market_prices[market_id]

        # 计算到期时间
        # 假设市场是 15 分钟周期
        time_to_expiry = market.expiry_minutes / (60 * 24 * 365)  # 转换为年

        # 检查是否临近到期
        if market.expiry_minutes * 60 < self.config.expiry_buffer_seconds:
            return

        # 获取历史价格用于波动率计算
        historical_prices = []
        if self.data_feed:
            history = self.data_feed.feed.get_price_history(market.symbol + "USDT", limit=100)
            historical_prices = [t.price for t in history]

        # 分析定价
        yes_result, no_result = self.pricer.analyze_market(
            current_price=current_price,
            target_price=market.target_price,
            time_to_expiry=time_to_expiry,
            market_yes_price=market_yes_price,
            historical_prices=historical_prices,
            fee_rate=self.config.fee_rate
        )

        # 生成信号
        signal = self._generate_signal(market, yes_result, no_result)

        if signal:
            self.signals.append(signal)
            self.stats["signals_generated"] += 1

            if self.on_signal:
                await self._safe_callback(self.on_signal, signal)

    def _generate_signal(self, market: MarketConfig,
                        yes_result: PricingResult,
                        no_result: PricingResult) -> Optional[TradingSignal]:
        """生成交易信号"""
        # 检查置信度
        if yes_result.confidence < self.config.min_confidence:
            return None

        # 确定方向
        signal_type = SignalType.HOLD
        result = None

        if yes_result.edge > self.config.min_edge:
            signal_type = SignalType.BUY_YES
            result = yes_result
        elif no_result.edge > self.config.min_edge:
            signal_type = SignalType.BUY_NO
            result = no_result

        if signal_type == SignalType.HOLD:
            return None

        # 确定信号强度
        if result.edge > 0.05:
            strength = SignalStrength.VERY_STRONG
        elif result.edge > 0.03:
            strength = SignalStrength.STRONG
        elif result.edge > 0.02:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # 计算仓位大小
        position_size = self._calculate_position_size(result.edge, strength)

        # 计算止损止盈
        if signal_type == SignalType.BUY_YES:
            stop_loss = result.market_price * 0.7
            take_profit = result.market_price * 1.3
        else:
            stop_loss = result.market_price * 0.7
            take_profit = result.market_price * 1.3

        return TradingSignal(
            market_id=market.market_id,
            signal_type=signal_type,
            strength=strength,
            theoretical_price=result.theoretical_price,
            market_price=result.market_price,
            edge=result.edge,
            confidence=result.confidence,
            timestamp=time.time(),
            reason=f"理论价格 {result.theoretical_price:.4f} vs 市场 {result.market_price:.4f}, Edge: {result.edge:.2%}",
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

    def _calculate_position_size(self, edge: float, strength: SignalStrength) -> float:
        """计算仓位大小"""
        base_size = self.config.max_position_size

        # 根据 Kelly Criterion 简化版本
        # f* = edge / odds
        kelly_fraction = min(0.25, edge / 0.5)  # 限制最大 25%

        # 根据信号强度调整
        strength_multiplier = {
            SignalStrength.WEAK: 0.3,
            SignalStrength.MODERATE: 0.5,
            SignalStrength.STRONG: 0.7,
            SignalStrength.VERY_STRONG: 1.0
        }

        size = base_size * kelly_fraction * strength_multiplier[strength]
        return round(size, 2)

    async def _safe_callback(self, callback: Callable, *args):
        """安全执行回调"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"回调错误: {e}")

    def get_signals(self, limit: int = 10) -> List[TradingSignal]:
        """获取最近的信号"""
        return self.signals[-limit:]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = self.stats["win_count"] + self.stats["loss_count"]
        win_rate = self.stats["win_count"] / total if total > 0 else 0

        return {
            **self.stats,
            "win_rate": f"{win_rate:.1%}",
            "markets_tracked": len(self.markets)
        }


class ExpiryRiskManager:
    """
    到期风险管理

    警告：
    - 除非有极强理由，否则不要在临近到期时购买高价期权
    - 一旦价格在最后一秒反转，会损失全部本金
    """

    def __init__(self, buffer_seconds: float = 60.0, max_price: float = 0.95):
        """
        Args:
            buffer_seconds: 到期前多少秒停止交易
            max_price: 最高可接受价格 (避免高价期权)
        """
        self.buffer_seconds = buffer_seconds
        self.max_price = max_price

    def check_expiry_risk(self, time_to_expiry_seconds: float, market_price: float) -> tuple:
        """
        检查到期风险

        Returns:
            (is_safe, risk_message)
        """
        # 检查是否临近到期
        if time_to_expiry_seconds < self.buffer_seconds:
            return False, f"⚠️ 临近到期 ({time_to_expiry_seconds:.0f}秒)，不建议交易"

        # 检查是否是高价期权
        if market_price > self.max_price:
            return False, f"⚠️ 价格过高 ({market_price:.2%})，风险极大"

        # 检查是否是低价期权 (同样风险)
        if market_price < (1 - self.max_price):
            return False, f"⚠️ 价格过低 ({market_price:.2%})，风险极大"

        return True, "✅ 风险可控"

    def calculate_time_risk(self, time_to_expiry_seconds: float) -> float:
        """
        计算时间风险系数 (0-1, 越高越危险)
        """
        if time_to_expiry_seconds <= 0:
            return 1.0

        if time_to_expiry_seconds < 60:
            return 0.9  # 1分钟内，极高风险

        if time_to_expiry_seconds < 300:
            return 0.6  # 5分钟内，高风险

        if time_to_expiry_seconds < 900:
            return 0.3  # 15分钟内，中等风险

        return 0.1  # 15分钟以上，低风险


class TakerExecutionEngine:
    """
    吃单执行引擎

    处理信号执行和订单管理
    """

    def __init__(self, strategy: TakerStrategy):
        self.strategy = strategy
        self.pending_orders: Dict[str, TradingSignal] = {}
        self.executed_orders: List[TradingSignal] = []
        self.simulation_mode = True

    async def execute_signal(self, signal: TradingSignal) -> Dict:
        """
        执行交易信号

        Args:
            signal: 交易信号

        Returns:
            执行结果
        """
        market_id = signal.market_id

        # 检查是否有待处理订单
        if market_id in self.pending_orders:
            return {"status": "error", "message": "已有待处理订单"}

        if self.simulation_mode:
            # 模拟执行
            result = {
                "status": "success",
                "mode": "simulation",
                "market_id": market_id,
                "signal_type": signal.signal_type.value,
                "position_size": signal.position_size,
                "price": signal.market_price,
                "timestamp": datetime.now().isoformat(),
                "message": f"模拟执行: {signal.signal_type.value} ${signal.position_size}"
            }
        else:
            # 实际执行 - 需要连接 Polymarket API
            result = await self._execute_real(signal)

        # 记录
        if result["status"] == "success":
            self.executed_orders.append(signal)
            self.strategy.last_trade_time[market_id] = time.time()
            self.strategy.stats["signals_executed"] += 1

        return result

    async def _execute_real(self, signal: TradingSignal) -> Dict:
        """实际执行交易 (需要实现)"""
        # TODO: 连接 Polymarket API 执行订单
        return {
            "status": "not_implemented",
            "message": "实际交易未实现，请使用模拟模式"
        }

    def get_open_positions(self) -> List[TradingSignal]:
        """获取当前持仓"""
        return list(self.pending_orders.values())

    def get_execution_history(self, limit: int = 20) -> List[Dict]:
        """获取执行历史"""
        return [
            {
                "market_id": s.market_id,
                "signal_type": s.signal_type.value,
                "position_size": s.position_size,
                "price": s.market_price,
                "edge": f"{s.edge:.2%}",
                "timestamp": datetime.fromtimestamp(s.timestamp).isoformat()
            }
            for s in self.executed_orders[-limit:]
        ]


# 使用示例
if __name__ == "__main__":
    async def main():
        # 创建策略
        config = TakerConfig(
            min_edge=0.02,      # 2% 最小优势
            min_confidence=0.5,
            max_position_size=100
        )
        strategy = TakerStrategy(config)

        # 添加市场
        strategy.add_market(MarketConfig(
            market_id="btc_15m_up",
            symbol="BTC",
            target_price=95000,  # 当前价格作为目标
            expiry_minutes=15
        ))

        # 设置信号回调
        async def on_signal(signal: TradingSignal):
            print(f"\n🔔 交易信号!")
            print(f"  市场: {signal.market_id}")
            print(f"  方向: {signal.signal_type.value}")
            print(f"  强度: {signal.strength.value}")
            print(f"  Edge: {signal.edge:.2%}")
            print(f"  仓位: ${signal.position_size}")
            print(f"  原因: {signal.reason}")

        strategy.on_signal = on_signal

        # 启动
        await strategy.start(["BTCUSDT"])

        # 运行 60 秒
        print("运行中... (60秒)")
        await asyncio.sleep(60)

        # 统计
        print("\n📊 统计:", strategy.get_stats())

        await strategy.stop()

    asyncio.run(main())

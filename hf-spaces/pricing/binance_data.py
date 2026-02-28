"""
Binance 实时数据源

直接从 Binance 获取实时价格，比 Chainlink 预言机更快
- WebSocket 实时价格流
- REST API 备用
- 高频数据收集
"""
import asyncio
import json
import time
from typing import Dict, List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import deque
import aiohttp
from loguru import logger


@dataclass
class PriceTick:
    """价格 Tick 数据"""
    symbol: str
    price: float
    timestamp: float
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0


@dataclass
class KlineData:
    """K线数据"""
    symbol: str
    interval: str
    open_time: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: float


class BinanceDataFeed:
    """
    Binance 实时数据源

    使用 WebSocket 获取毫秒级延迟的价格数据
    比 Chainlink 预言机（每秒更新一次）快得多
    """

    # Binance WebSocket 端点
    WS_BASE = "wss://stream.binance.com:9443/ws"
    WS_FUTURE = "wss://fstream.binance.com/ws"  # 期货

    # REST API 端点
    REST_BASE = "https://api.binance.com/api/v3"
    REST_FUTURE = "https://fapi.binance.com/fapi/v1"

    def __init__(self, use_futures: bool = False):
        """
        初始化数据源

        Args:
            use_futures: 是否使用期货数据 (更准确反映预测市场)
        """
        self.use_futures = use_futures
        self.ws_base = self.WS_FUTURE if use_futures else self.WS_BASE
        self.rest_base = self.REST_FUTURE if use_futures else self.REST_BASE

        # 连接状态
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False

        # 数据存储
        self.prices: Dict[str, PriceTick] = {}
        self.price_history: Dict[str, deque] = {}  # 价格历史
        self.kline_history: Dict[str, deque] = {}  # K线历史

        # 回调函数
        self.on_price_update: Optional[Callable] = None
        self.on_kline_update: Optional[Callable] = None

        # 配置
        self.history_size = 1000  # 保留的历史数据量
        self.reconnect_delay = 5

    async def connect(self):
        """建立 WebSocket 连接"""
        if self.session is None:
            self.session = aiohttp.ClientSession()

        try:
            self.ws = await self.session.ws_connect(self.ws_base)
            self.running = True
            logger.info(f"✅ Binance WebSocket 连接成功 ({'期货' if self.use_futures else '现货'})")
        except Exception as e:
            logger.error(f"❌ WebSocket 连接失败: {e}")
            raise

    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

    async def subscribe_ticker(self, symbols: List[str]):
        """
        订阅实时价格

        Args:
            symbols: 交易对列表，如 ["btcusdt", "ethusdt"]
        """
        if not self.ws:
            await self.connect()

        # 构建订阅消息
        streams = [f"{s.lower()}@ticker" for s in symbols]
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }

        await self.ws.send_json(msg)
        logger.info(f"📊 订阅价格: {symbols}")

        # 初始化价格历史
        for s in symbols:
            key = s.upper()
            if key not in self.price_history:
                self.price_history[key] = deque(maxlen=self.history_size)

    async def subscribe_klines(self, symbols: List[str], interval: str = "1m"):
        """
        订阅 K 线数据

        Args:
            symbols: 交易对列表
            interval: K线周期 (1m, 5m, 15m, 1h, etc.)
        """
        if not self.ws:
            await self.connect()

        streams = [f"{s.lower()}@kline_{interval}" for s in symbols]
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }

        await self.ws.send_json(msg)
        logger.info(f"📈 订阅 K线: {symbols} ({interval})")

        # 初始化 K 线历史
        for s in symbols:
            key = f"{s.upper()}_{interval}"
            if key not in self.kline_history:
                self.kline_history[key] = deque(maxlen=self.history_size)

    async def subscribe_agg_trades(self, symbols: List[str]):
        """
        订阅聚合交易流 (最快的价格更新)

        这是获取价格的最快方式，延迟最低
        """
        if not self.ws:
            await self.connect()

        streams = [f"{s.lower()}@aggTrade" for s in symbols]
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time())
        }

        await self.ws.send_json(msg)
        logger.info(f"⚡ 订阅聚合交易: {symbols}")

    async def listen(self):
        """监听 WebSocket 消息"""
        if not self.ws:
            await self.connect()

        while self.running:
            try:
                msg = await self.ws.receive()

                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._process_message(data)

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {self.ws.exception()}")
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    logger.warning("WebSocket 连接关闭")
                    break

            except Exception as e:
                logger.error(f"消息处理错误: {e}")
                await asyncio.sleep(0.1)

        # 自动重连
        if self.running:
            logger.info(f"🔄 {self.reconnect_delay}秒后重新连接...")
            await asyncio.sleep(self.reconnect_delay)
            await self.connect()

    async def _process_message(self, data: dict):
        """处理 WebSocket 消息"""
        # 聚合交易 (最快)
        if "e" in data and data["e"] == "aggTrade":
            await self._process_agg_trade(data)

        # 24hr Ticker
        elif "e" in data and data["e"] == "24hrTicker":
            await self._process_ticker(data)

        # K线
        elif "e" in data and data["e"] == "kline":
            await self._process_kline(data)

    async def _process_agg_trade(self, data: dict):
        """处理聚合交易数据"""
        symbol = data.get("s", "")
        price = float(data.get("p", 0))
        timestamp = data.get("T", time.time() * 1000) / 1000
        volume = float(data.get("q", 0))

        # 更新价格
        tick = PriceTick(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            volume=volume
        )
        self.prices[symbol] = tick

        # 添加到历史
        if symbol in self.price_history:
            self.price_history[symbol].append(tick)

        # 触发回调
        if self.on_price_update:
            await self._safe_callback(self.on_price_update, tick)

    async def _process_ticker(self, data: dict):
        """处理 Ticker 数据"""
        symbol = data.get("s", "")
        price = float(data.get("c", 0))  # 最新价
        bid = float(data.get("b", 0))    # 最佳买价
        ask = float(data.get("a", 0))    # 最佳卖价
        timestamp = time.time()

        tick = PriceTick(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            bid=bid,
            ask=ask
        )
        self.prices[symbol] = tick

        if symbol in self.price_history:
            self.price_history[symbol].append(tick)

        if self.on_price_update:
            await self._safe_callback(self.on_price_update, tick)

    async def _process_kline(self, data: dict):
        """处理 K 线数据"""
        k = data.get("k", {})
        symbol = k.get("s", "")
        interval = k.get("i", "")

        kline = KlineData(
            symbol=symbol,
            interval=interval,
            open_time=k.get("t", 0) / 1000,
            open=float(k.get("o", 0)),
            high=float(k.get("h", 0)),
            low=float(k.get("l", 0)),
            close=float(k.get("c", 0)),
            volume=float(k.get("v", 0)),
            close_time=k.get("T", 0) / 1000
        )

        key = f"{symbol}_{interval}"
        if key in self.kline_history:
            self.kline_history[key].append(kline)

        if self.on_kline_update:
            await self._safe_callback(self.on_kline_update, kline)

    async def _safe_callback(self, callback: Callable, *args):
        """安全执行回调"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"回调错误: {e}")

    # ==================== REST API 方法 ====================

    async def get_price(self, symbol: str) -> Optional[PriceTick]:
        """
        通过 REST API 获取价格 (备用)

        Args:
            symbol: 交易对，如 "BTCUSDT"
        """
        if self.session is None:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.rest_base}/ticker/price"
            params = {"symbol": symbol.upper()}

            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                return PriceTick(
                    symbol=data["symbol"],
                    price=float(data["price"]),
                    timestamp=time.time()
                )
        except Exception as e:
            logger.error(f"REST 获取价格失败: {e}")
            return None

    async def get_klines(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[KlineData]:
        """
        获取历史 K 线数据

        Args:
            symbol: 交易对
            interval: K线周期
            limit: 数量
        """
        if self.session is None:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.rest_base}/klines"
            params = {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit
            }

            async with self.session.get(url, params=params) as resp:
                data = await resp.json()

                klines = []
                for k in data:
                    klines.append(KlineData(
                        symbol=symbol.upper(),
                        interval=interval,
                        open_time=k[0] / 1000,
                        open=float(k[1]),
                        high=float(k[2]),
                        low=float(k[3]),
                        close=float(k[4]),
                        volume=float(k[5]),
                        close_time=k[6] / 1000
                    ))

                return klines
        except Exception as e:
            logger.error(f"获取 K 线失败: {e}")
            return []

    # ==================== 数据访问方法 ====================

    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        tick = self.prices.get(symbol.upper())
        return tick.price if tick else None

    def get_price_history(self, symbol: str, limit: int = 100) -> List[PriceTick]:
        """获取价格历史"""
        history = self.price_history.get(symbol.upper(), deque())
        return list(history)[-limit:]

    def get_kline_history(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[KlineData]:
        """获取 K 线历史"""
        key = f"{symbol.upper()}_{interval}"
        history = self.kline_history.get(key, deque())
        return list(history)[-limit:]

    def get_high_low_prices(self, symbol: str, interval: str = "1m", limit: int = 20) -> tuple:
        """
        获取高低价历史 (用于波动率计算)

        Returns:
            (highs, lows)
        """
        klines = self.get_kline_history(symbol, interval, limit)
        if not klines:
            return [], []

        highs = [k.high for k in klines]
        lows = [k.low for k in klines]
        return highs, lows


class MultiSymbolDataFeed:
    """
    多币种数据源

    同时管理多个币种的实时数据
    """

    def __init__(self, symbols: List[str] = None, use_futures: bool = True):
        """
        Args:
            symbols: 默认监控的币种
            use_futures: 使用期货数据
        """
        self.feed = BinanceDataFeed(use_futures=use_futures)
        self.symbols = symbols or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        self.price_callbacks: List[Callable] = []

    async def start(self):
        """启动数据源"""
        await self.feed.connect()

        # 订阅聚合交易 (最快)
        await self.feed.subscribe_agg_trades(self.symbols)

        # 订阅 K 线 (用于波动率计算)
        await self.feed.subscribe_klines(self.symbols, "1m")

        # 设置回调
        self.feed.on_price_update = self._on_price

        # 开始监听
        asyncio.create_task(self.feed.listen())

        logger.info(f"🚀 多币种数据源启动: {self.symbols}")

    async def _on_price(self, tick: PriceTick):
        """价格更新回调"""
        for callback in self.price_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(tick)
                else:
                    callback(tick)
            except Exception as e:
                logger.error(f"价格回调错误: {e}")

    def add_price_callback(self, callback: Callable):
        """添加价格回调"""
        self.price_callbacks.append(callback)

    def get_price(self, symbol: str) -> Optional[float]:
        """获取价格"""
        return self.feed.get_current_price(symbol)

    def get_all_prices(self) -> Dict[str, float]:
        """获取所有价格"""
        return {
            symbol: self.feed.get_current_price(symbol)
            for symbol in self.symbols
            if self.feed.get_current_price(symbol) is not None
        }

    async def stop(self):
        """停止数据源"""
        await self.feed.disconnect()


# 使用示例
if __name__ == "__main__":
    async def main():
        feed = MultiSymbolDataFeed(["BTCUSDT", "ETHUSDT"], use_futures=True)

        def on_price(tick: PriceTick):
            print(f"[{tick.symbol}] ${tick.price:,.2f} @ {datetime.fromtimestamp(tick.timestamp)}")

        feed.add_price_callback(on_price)
        await feed.start()

        # 运行 30 秒
        await asyncio.sleep(30)

        print("\n所有价格:", feed.get_all_prices())
        await feed.stop()

    asyncio.run(main())

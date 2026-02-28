"""
Alpha Data Sources - 实时数据源优化

关键洞察:
- Polymarket 使用 Chainlink 预言机进行结算 (15分钟/5分钟周期)
- Chainlink 每秒仅更新一次，有滞后性
- 直接使用 Binance 实时数据可以"偷跑"并捕获定价错误

数据源优先级:
1. Binance WebSocket (最快，< 10ms)
2. Binance REST API (较快，~100ms)
3. Chainlink 预言机 (慢，~1s 更新)
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable
from enum import Enum
import logging

import aiohttp
import websockets

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据源类型"""
    BINANCE_WS = "binance_websocket"
    BINANCE_REST = "binance_rest"
    CHAINLINK = "chainlink"
    COINGECKO = "coingecko"


@dataclass
class PriceTick:
    """价格数据"""
    source: DataSource
    symbol: str
    price: float
    timestamp: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None


@dataclass
class KlineData:
    """K线数据"""
    symbol: str
    interval: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


class BinanceWebSocketClient:
    """
    Binance WebSocket 客户端

    获取实时价格数据，延迟 < 10ms
    这是获取 Alpha 的关键数据源
    """

    WS_BASE = "wss://stream.binance.com:9443/ws"
    WS_COMBINED = "wss://stream.binance.com:9443/stream"

    SYMBOLS = {
        "BTCUSDT": "btc",
        "ETHUSDT": "eth",
        "SOLUSDT": "sol",
        "XRPUSDT": "xrp",
        "DOGEUSDT": "doge",
    }

    def __init__(self):
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.prices: Dict[str, PriceTick] = {}
        self.klines: Dict[str, List[KlineData]] = {}
        self.callbacks: List[Callable[[PriceTick], None]] = []
        self.reconnect_interval = 5

    async def connect(self, symbols: List[str] = None):
        """连接到 Binance WebSocket"""
        if symbols is None:
            symbols = list(self.SYMBOLS.keys())

        streams = []
        for symbol in symbols:
            symbol_lower = symbol.lower()
            streams.append(f"{symbol_lower}@ticker")
            streams.append(f"{symbol_lower}@kline_1m")
            streams.append(f"{symbol_lower}@bookTicker")

        stream_url = f"{self.WS_COMBINED}?streams={'/'.join(streams)}"

        logger.info(f"Connecting to Binance WebSocket: {len(streams)} streams")

        self.running = True
        while self.running:
            try:
                async with websockets.connect(stream_url) as ws:
                    self.ws = ws
                    logger.info("Connected to Binance WebSocket")

                    async for message in ws:
                        if not self.running:
                            break
                        await self._handle_message(message)

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    await asyncio.sleep(self.reconnect_interval)

    async def _handle_message(self, message: str):
        """处理 WebSocket 消息"""
        try:
            data = json.loads(message)
            stream_data = data.get("data", data)
            stream = data.get("stream", "")

            now = time.time()

            if "@ticker" in stream:
                ticker = stream_data
                symbol = ticker.get("s", "")
                price = float(ticker.get("c", 0))
                bid = float(ticker.get("b", 0))
                ask = float(ticker.get("a", 0))
                volume = float(ticker.get("v", 0))

                tick = PriceTick(
                    source=DataSource.BINANCE_WS,
                    symbol=symbol,
                    price=price,
                    timestamp=now,
                    bid=bid,
                    ask=ask,
                    volume=volume
                )

                self.prices[symbol] = tick

                for callback in self.callbacks:
                    try:
                        callback(tick)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

            elif "@kline_" in stream:
                kline_data = stream_data.get("k", {})
                if kline_data.get("x", False):
                    kline = KlineData(
                        symbol=kline_data.get("s", ""),
                        interval=kline_data.get("i", ""),
                        open_time=kline_data.get("t", 0),
                        open=float(kline_data.get("o", 0)),
                        high=float(kline_data.get("h", 0)),
                        low=float(kline_data.get("l", 0)),
                        close=float(kline_data.get("c", 0)),
                        volume=float(kline_data.get("v", 0)),
                        close_time=kline_data.get("T", 0)
                    )

                    symbol = kline.symbol
                    if symbol not in self.klines:
                        self.klines[symbol] = []
                    self.klines[symbol].append(kline)

                    if len(self.klines[symbol]) > 100:
                        self.klines[symbol] = self.klines[symbol][-100:]

            elif "@bookTicker" in stream:
                book = stream_data
                symbol = book.get("s", "")
                if symbol in self.prices:
                    self.prices[symbol].bid = float(book.get("b", 0))
                    self.prices[symbol].ask = float(book.get("a", 0))

        except Exception as e:
            logger.error(f"Message handling error: {e}")

    def add_callback(self, callback: Callable[[PriceTick], None]):
        """添加价格更新回调"""
        self.callbacks.append(callback)

    def get_price(self, symbol: str) -> Optional[PriceTick]:
        """获取最新价格"""
        return self.prices.get(symbol)

    def get_klines(self, symbol: str, limit: int = 20) -> List[KlineData]:
        """获取 K 线数据"""
        if symbol in self.klines:
            return self.klines[symbol][-limit:]
        return []

    async def close(self):
        """关闭连接"""
        self.running = False
        if self.ws:
            await self.ws.close()


class BinanceRestClient:
    """Binance REST API 客户端"""

    API_BASE = "https://api.binance.com/api/v3"

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def get_price(self, symbol: str = "BTCUSDT") -> PriceTick:
        """获取当前价格"""
        session = await self._get_session()
        url = f"{self.API_BASE}/ticker/price?symbol={symbol}"

        async with session.get(url) as resp:
            data = await resp.json()

        return PriceTick(
            source=DataSource.BINANCE_REST,
            symbol=symbol,
            price=float(data.get("price", 0)),
            timestamp=time.time()
        )

    async def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1m",
        limit: int = 100
    ) -> List[KlineData]:
        """获取 K 线数据"""
        session = await self._get_session()
        url = f"{self.API_BASE}/klines?symbol={symbol}&interval={interval}&limit={limit}"

        async with session.get(url) as resp:
            data = await resp.json()

        klines = []
        for k in data:
            klines.append(KlineData(
                symbol=symbol,
                interval=interval,
                open_time=k[0],
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                close_time=k[6]
            ))

        return klines

    async def get_ticker_24h(self, symbol: str = "BTCUSDT") -> Dict:
        """获取 24 小时行情"""
        session = await self._get_session()
        url = f"{self.API_BASE}/ticker/24hr?symbol={symbol}"

        async with session.get(url) as resp:
            return await resp.json()

    async def close(self):
        """关闭会话"""
        if self.session and not self.session.closed:
            await self.session.close()


class AlphaSourceManager:
    """Alpha 数据源管理器"""

    def __init__(self):
        self.binance_ws = BinanceWebSocketClient()
        self.binance_rest = BinanceRestClient()

        self.best_prices: Dict[str, PriceTick] = {}
        self.price_history: Dict[str, List[float]] = {}
        self.alpha_callbacks: List[Callable] = []

        self.running = False

    async def start(self, symbols: List[str] = None):
        """启动数据源"""
        self.running = True
        asyncio.create_task(self.binance_ws.connect(symbols))
        asyncio.create_task(self._monitor_prices())
        logger.info("Alpha Source Manager started")

    async def _monitor_prices(self):
        """监控价格更新"""
        while self.running:
            try:
                for symbol, tick in self.binance_ws.prices.items():
                    self.best_prices[symbol] = tick

                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    self.price_history[symbol].append(tick.price)

                    if len(self.price_history[symbol]) > 1000:
                        self.price_history[symbol] = self.price_history[symbol][-1000:]

                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Price monitoring error: {e}")
                await asyncio.sleep(1)

    def get_price(self, symbol: str) -> Optional[PriceTick]:
        """获取最新价格"""
        return self.best_prices.get(symbol)

    def get_price_history(self, symbol: str, limit: int = 100) -> List[float]:
        """获取历史价格"""
        if symbol in self.price_history:
            return self.price_history[symbol][-limit:]
        return []

    async def stop(self):
        """停止数据源"""
        self.running = False
        await self.binance_ws.close()
        await self.binance_rest.close()

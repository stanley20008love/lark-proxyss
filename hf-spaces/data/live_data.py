"""
实时数据获取模块 (Live Data Fetcher)

获取 Polymarket 和加密货币实时数据
支持模拟交易模式 - 使用实时数据但模拟执行
"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """数据源"""
    POLYMARKET = "polymarket"
    BINANCE = "binance"
    COINGECKO = "coingecko"
    MOCK = "mock"


@dataclass
class MarketData:
    """市场数据"""
    market_id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float
    volume_24h: float
    timestamp: datetime
    source: DataSource
    additional_data: Dict = field(default_factory=dict)


@dataclass
class CryptoPrice:
    """加密货币价格"""
    symbol: str
    price: float
    change_24h: float
    volume_24h: float
    timestamp: datetime
    source: DataSource


class PolymarketDataFetcher:
    """
    Polymarket 数据获取器
    
    获取实时市场数据，但交易以模拟模式执行
    """
    
    API_BASE = "https://clob.polymarket.com"
    
    # 缓存设置
    CACHE_DURATION = 30  # 秒
    
    def __init__(self, simulation_mode: bool = True):
        self.session: Optional[aiohttp.ClientSession] = None
        self.simulation_mode = simulation_mode
        
        # 缓存
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, float] = {}
        
        # 数据存储
        self.markets: List[MarketData] = []
        self.last_update: Optional[datetime] = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP 会话"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache_time:
            return False
        return time.time() - self._cache_time[key] < self.CACHE_DURATION
    
    async def fetch_markets(self, limit: int = 50) -> List[MarketData]:
        """获取市场列表"""
        cache_key = f"markets_{limit}"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            session = await self._get_session()
            url = f"{self.API_BASE}/markets"
            
            async with session.get(url, params={"limit": limit}, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    markets = self._parse_markets(data.get("results", []))
                    
                    # 更新缓存
                    self._cache[cache_key] = markets
                    self._cache_time[cache_key] = time.time()
                    self.markets = markets
                    self.last_update = datetime.now()
                    
                    logger.info(f"✅ 获取到 {len(markets)} 个市场")
                    return markets
                else:
                    logger.warning(f"API 返回错误: {resp.status}")
                    return self._get_fallback_markets()
                    
        except asyncio.TimeoutError:
            logger.warning("API 请求超时，使用缓存数据")
            return self._get_fallback_markets()
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return self._get_fallback_markets()
    
    def _parse_markets(self, raw_data: List[Dict]) -> List[MarketData]:
        """解析市场数据"""
        markets = []
        
        for item in raw_data:
            try:
                # 解析价格
                yes_price = float(item.get("outcome_prices", ["0.5"])[0])
                no_price = 1.0 - yes_price
                
                market = MarketData(
                    market_id=item.get("condition_id", item.get("id", "")),
                    question=item.get("question", "Unknown"),
                    yes_price=yes_price,
                    no_price=no_price,
                    liquidity=float(item.get("liquidity", 0)),
                    volume_24h=float(item.get("volume", 0)),
                    timestamp=datetime.now(),
                    source=DataSource.POLYMARKET,
                    additional_data={
                        "slug": item.get("slug", ""),
                        "tags": item.get("tags", []),
                        "active": item.get("active", True)
                    }
                )
                markets.append(market)
            except Exception as e:
                logger.debug(f"解析市场失败: {e}")
                continue
        
        return markets
    
    def _get_fallback_markets(self) -> List[MarketData]:
        """获取备用市场数据"""
        # 如果有缓存，返回缓存
        if self.markets:
            return self.markets
        
        # 否则返回模拟数据
        return [
            MarketData(
                market_id="btc_100k",
                question="BTC 达到 $100,000?",
                yes_price=0.72,
                no_price=0.28,
                liquidity=150000,
                volume_24h=50000,
                timestamp=datetime.now(),
                source=DataSource.MOCK
            ),
            MarketData(
                market_id="eth_5k",
                question="ETH 突破 $5,000?",
                yes_price=0.45,
                no_price=0.55,
                liquidity=80000,
                volume_24h=30000,
                timestamp=datetime.now(),
                source=DataSource.MOCK
            ),
            MarketData(
                market_id="sol_200",
                question="SOL 突破 $200?",
                yes_price=0.58,
                no_price=0.42,
                liquidity=50000,
                volume_24h=20000,
                timestamp=datetime.now(),
                source=DataSource.MOCK
            ),
        ]
    
    async def fetch_market_price(self, token_id: str) -> Optional[float]:
        """获取特定市场价格"""
        cache_key = f"price_{token_id}"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            session = await self._get_session()
            url = f"{self.API_BASE}/price"
            
            async with session.get(url, params={"token_id": token_id}, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = float(data.get("price", 0.5))
                    
                    self._cache[cache_key] = price
                    self._cache_time[cache_key] = time.time()
                    
                    return price
        except Exception as e:
            logger.error(f"获取价格失败: {e}")
        
        return None
    
    async def search_crypto_markets(self, keyword: str = "btc") -> List[MarketData]:
        """搜索加密货币相关市场"""
        markets = await self.fetch_markets(limit=100)
        
        # 过滤包含关键词的市场
        keyword_lower = keyword.lower()
        filtered = [
            m for m in markets
            if keyword_lower in m.question.lower()
        ]
        
        return filtered
    
    async def close(self):
        """关闭连接"""
        if self.session and not self.session.closed:
            await self.session.close()


class BinancePriceFetcher:
    """
    Binance 价格获取器
    
    获取加密货币实时价格
    """
    
    API_BASE = "https://api.binance.com/api/v3"
    CACHE_DURATION = 5  # 秒
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_time: Dict[str, float] = {}
        self.prices: Dict[str, CryptoPrice] = {}
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache_time:
            return False
        return time.time() - self._cache_time[key] < self.CACHE_DURATION
    
    async def fetch_price(self, symbol: str = "BTCUSDT") -> Optional[CryptoPrice]:
        """获取价格"""
        cache_key = f"price_{symbol}"
        
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key]
        
        try:
            session = await self._get_session()
            
            # 获取当前价格
            url = f"{self.API_BASE}/ticker/price"
            async with session.get(url, params={"symbol": symbol}, timeout=5) as resp:
                price_data = await resp.json()
            
            # 获取 24h 变化
            url = f"{self.API_BASE}/ticker/24hr"
            async with session.get(url, params={"symbol": symbol}, timeout=5) as resp:
                ticker_data = await resp.json()
            
            crypto_price = CryptoPrice(
                symbol=symbol,
                price=float(price_data.get("price", 0)),
                change_24h=float(ticker_data.get("priceChangePercent", 0)),
                volume_24h=float(ticker_data.get("volume", 0)),
                timestamp=datetime.now(),
                source=DataSource.BINANCE
            )
            
            self._cache[cache_key] = crypto_price
            self._cache_time[cache_key] = time.time()
            self.prices[symbol] = crypto_price
            
            return crypto_price
            
        except Exception as e:
            logger.error(f"获取 {symbol} 价格失败: {e}")
            # 返回缓存或默认值
            if symbol in self.prices:
                return self.prices[symbol]
            return None
    
    async def fetch_all_prices(self, symbols: List[str] = None) -> Dict[str, CryptoPrice]:
        """获取多个币种价格"""
        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
        
        results = {}
        for symbol in symbols:
            price = await self.fetch_price(symbol)
            if price:
                results[symbol] = price
        
        return results
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


class LiveDataManager:
    """
    实时数据管理器
    
    统一管理所有数据源
    """
    
    def __init__(self, simulation_mode: bool = True):
        self.simulation_mode = simulation_mode
        self.polymarket = PolymarketDataFetcher(simulation_mode)
        self.binance = BinancePriceFetcher()
        
        self._running = False
        self._update_interval = 30  # 秒
        
        # 数据存储
        self.crypto_prices: Dict[str, CryptoPrice] = {}
        self.markets: List[MarketData] = []
    
    async def start(self):
        """启动数据更新"""
        self._running = True
        logger.info(f"📊 数据管理器启动 (模拟模式: {self.simulation_mode})")
        
        # 初始加载
        await self.refresh_all()
    
    async def refresh_all(self):
        """刷新所有数据"""
        try:
            # 并行获取
            results = await asyncio.gather(
                self.polymarket.fetch_markets(limit=50),
                self.binance.fetch_all_prices(),
                return_exceptions=True
            )
            
            # 处理结果
            if not isinstance(results[0], Exception):
                self.markets = results[0]
            
            if not isinstance(results[1], Exception):
                self.crypto_prices = results[1]
            
            logger.info(f"✅ 数据刷新完成: {len(self.markets)} 市场, {len(self.crypto_prices)} 价格")
            
        except Exception as e:
            logger.error(f"数据刷新失败: {e}")
    
    async def stop(self):
        """停止数据更新"""
        self._running = False
        await self.polymarket.close()
        await self.binance.close()
    
    def get_market_by_id(self, market_id: str) -> Optional[MarketData]:
        """获取特定市场"""
        for market in self.markets:
            if market.market_id == market_id:
                return market
        return None
    
    def get_crypto_price(self, symbol: str) -> Optional[CryptoPrice]:
        """获取加密货币价格"""
        # 尝试完整符号
        if symbol in self.crypto_prices:
            return self.crypto_prices[symbol]
        
        # 尝试添加 USDT 后缀
        if f"{symbol}USDT" in self.crypto_prices:
            return self.crypto_prices[f"{symbol}USDT"]
        
        return None
    
    def get_dashboard_data(self) -> Dict:
        """获取仪表盘数据"""
        return {
            "simulation_mode": self.simulation_mode,
            "markets_count": len(self.markets),
            "crypto_prices": {
                symbol: {
                    "price": p.price,
                    "change_24h": f"{p.change_24h:+.2f}%"
                }
                for symbol, p in self.crypto_prices.items()
            },
            "last_update": datetime.now().isoformat(),
            "data_sources": {
                "polymarket": "live" if self.markets and self.markets[0].source == DataSource.POLYMARKET else "fallback",
                "binance": "live" if self.crypto_prices else "unavailable"
            }
        }


# 全局实例
live_data = LiveDataManager(simulation_mode=True)

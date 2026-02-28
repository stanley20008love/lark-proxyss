"""
WebSocket 实时行情订阅模块

支持多平台实时数据：
- Polymarket
- Predict.fun
"""
import asyncio
import json
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import websockets
from loguru import logger


class Platform(Enum):
    """平台"""
    POLYMARKET = "polymarket"
    PREDICT_FUN = "predict_fun"


@dataclass
class PriceUpdate:
    """价格更新"""
    platform: Platform
    market_id: str
    token_id: str
    yes_price: float
    no_price: float
    best_bid: float
    best_ask: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderbookUpdate:
    """订单簿更新"""
    platform: Platform
    market_id: str
    token_id: str
    bids: List[Dict]  # [{"price": "0.45", "size": "100"}, ...]
    asks: List[Dict]
    timestamp: datetime = field(default_factory=datetime.now)


class WebSocketClient:
    """WebSocket 客户端"""
    
    def __init__(self, platform: Platform, ws_url: str):
        self.platform = platform
        self.ws_url = ws_url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.reconnect_interval = 5
        self.heartbeat_interval = 30
        
        # 订阅的市场
        self.subscribed_markets: Dict[str, bool] = {}
        
        # 回调函数
        self.on_price_update: Optional[Callable[[PriceUpdate], None]] = None
        self.on_orderbook_update: Optional[Callable[[OrderbookUpdate], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None
        
        # 统计
        self.stats = {
            "messages_received": 0,
            "reconnects": 0,
            "last_message_time": None
        }
    
    async def connect(self):
        """连接 WebSocket"""
        while self.running:
            try:
                logger.info(f"🔌 连接 {self.platform.value} WebSocket: {self.ws_url}")
                
                async with websockets.connect(self.ws_url) as ws:
                    self.ws = ws
                    logger.info(f"✅ {self.platform.value} WebSocket 连接成功")
                    
                    if self.on_connected:
                        self.on_connected()
                    
                    # 重新订阅
                    await self._resubscribe()
                    
                    # 启动心跳
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                    
                    try:
                        async for message in ws:
                            await self._handle_message(message)
                    except websockets.ConnectionClosed:
                        logger.warning(f"⚠️ {self.platform.value} WebSocket 连接关闭")
                    finally:
                        heartbeat_task.cancel()
                    
                    if self.on_disconnected:
                        self.on_disconnected()
                
            except Exception as e:
                logger.error(f"❌ {self.platform.value} WebSocket 错误: {e}")
                self.stats["reconnects"] += 1
            
            if self.running:
                logger.info(f"🔄 {self.platform.value} {self.reconnect_interval} 秒后重连...")
                await asyncio.sleep(self.reconnect_interval)
    
    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.ws:
            await self.ws.close()
    
    async def subscribe_market(self, market_id: str, token_id: str):
        """订阅市场"""
        key = f"{market_id}_{token_id}"
        self.subscribed_markets[key] = True
        
        if self.ws:
            await self._send_subscribe(market_id, token_id)
    
    async def unsubscribe_market(self, market_id: str, token_id: str):
        """取消订阅"""
        key = f"{market_id}_{token_id}"
        if key in self.subscribed_markets:
            del self.subscribed_markets[key]
        
        if self.ws:
            await self._send_unsubscribe(market_id, token_id)
    
    async def _send_subscribe(self, market_id: str, token_id: str):
        """发送订阅消息"""
        if self.platform == Platform.POLYMARKET:
            msg = {
                "type": "subscribe",
                "channel": "market",
                "markets": [market_id]
            }
        else:  # PREDICT_FUN
            msg = {
                "type": "subscribe",
                "channel": "orderbook",
                "token_id": token_id
            }
        
        await self.ws.send(json.dumps(msg))
        logger.debug(f"📡 订阅: {market_id}")
    
    async def _send_unsubscribe(self, market_id: str, token_id: str):
        """发送取消订阅消息"""
        if self.platform == Platform.POLYMARKET:
            msg = {
                "type": "unsubscribe",
                "channel": "market",
                "markets": [market_id]
            }
        else:
            msg = {
                "type": "unsubscribe",
                "channel": "orderbook",
                "token_id": token_id
            }
        
        await self.ws.send(json.dumps(msg))
    
    async def _resubscribe(self):
        """重新订阅所有市场"""
        for key in self.subscribed_markets:
            parts = key.split("_")
            if len(parts) >= 2:
                await self._send_subscribe(parts[0], parts[1])
    
    async def _handle_message(self, message: str):
        """处理消息"""
        self.stats["messages_received"] += 1
        self.stats["last_message_time"] = datetime.now().isoformat()
        
        try:
            data = json.loads(message)
            
            if self.platform == Platform.POLYMARKET:
                await self._handle_polymarket_message(data)
            else:
                await self._handle_predict_message(data)
                
        except json.JSONDecodeError:
            logger.warning(f"无法解析消息: {message[:100]}")
        except Exception as e:
            logger.error(f"处理消息错误: {e}")
    
    async def _handle_polymarket_message(self, data: Dict):
        """处理 Polymarket 消息"""
        msg_type = data.get("type")
        
        if msg_type == "market_update":
            market_id = data.get("market_id", "")
            asset_id = data.get("asset_id", "")
            
            # 解析价格
            yes_price = float(data.get("yes_price", 0))
            no_price = float(data.get("no_price", 0))
            best_bid = float(data.get("best_bid", 0))
            best_ask = float(data.get("best_ask", 0))
            
            update = PriceUpdate(
                platform=self.platform,
                market_id=market_id,
                token_id=asset_id,
                yes_price=yes_price,
                no_price=no_price,
                best_bid=best_bid,
                best_ask=best_ask
            )
            
            if self.on_price_update:
                self.on_price_update(update)
        
        elif msg_type == "orderbook_update":
            market_id = data.get("market_id", "")
            asset_id = data.get("asset_id", "")
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            update = OrderbookUpdate(
                platform=self.platform,
                market_id=market_id,
                token_id=asset_id,
                bids=bids,
                asks=asks
            )
            
            if self.on_orderbook_update:
                self.on_orderbook_update(update)
    
    async def _handle_predict_message(self, data: Dict):
        """处理 Predict.fun 消息"""
        msg_type = data.get("type")
        
        if msg_type == "orderbook_snapshot" or msg_type == "orderbook_delta":
            token_id = data.get("token_id", "")
            
            # 解析订单簿
            bids = data.get("bids", [])
            asks = data.get("asks", [])
            
            best_bid = float(bids[0]["price"]) if bids else 0
            best_ask = float(asks[0]["price"]) if asks else 1
            
            update = OrderbookUpdate(
                platform=self.platform,
                market_id=token_id,
                token_id=token_id,
                bids=bids,
                asks=asks
            )
            
            if self.on_orderbook_update:
                self.on_orderbook_update(update)
    
    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.running and self.ws:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.ws:
                    await self.ws.ping()
            except Exception as e:
                logger.debug(f"心跳错误: {e}")
    
    def start(self):
        """启动"""
        self.running = True
        return self.connect()
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return self.stats.copy()


class MultiPlatformWebSocket:
    """多平台 WebSocket 管理器"""
    
    def __init__(self):
        self.clients: Dict[Platform, WebSocketClient] = {}
        self.price_cache: Dict[str, PriceUpdate] = {}
        self.orderbook_cache: Dict[str, OrderbookUpdate] = {}
        
        self.on_price_update: Optional[Callable[[PriceUpdate], None]] = None
        self.on_orderbook_update: Optional[Callable[[OrderbookUpdate], None]] = None
    
    def add_client(self, platform: Platform, ws_url: str):
        """添加客户端"""
        client = WebSocketClient(platform, ws_url)
        
        client.on_price_update = self._handle_price_update
        client.on_orderbook_update = self._handle_orderbook_update
        
        self.clients[platform] = client
    
    def _handle_price_update(self, update: PriceUpdate):
        """处理价格更新"""
        key = f"{update.platform.value}_{update.token_id}"
        self.price_cache[key] = update
        
        if self.on_price_update:
            self.on_price_update(update)
    
    def _handle_orderbook_update(self, update: OrderbookUpdate):
        """处理订单簿更新"""
        key = f"{update.platform.value}_{update.token_id}"
        self.orderbook_cache[key] = update
        
        if self.on_orderbook_update:
            self.on_orderbook_update(update)
    
    async def start_all(self):
        """启动所有客户端"""
        tasks = [client.start() for client in self.clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self):
        """停止所有客户端"""
        for client in self.clients.values():
            await client.disconnect()
    
    async def subscribe_market(self, platform: Platform, market_id: str, token_id: str):
        """订阅市场"""
        if platform in self.clients:
            await self.clients[platform].subscribe_market(market_id, token_id)
    
    def get_latest_price(self, platform: Platform, token_id: str) -> Optional[PriceUpdate]:
        """获取最新价格"""
        key = f"{platform.value}_{token_id}"
        return self.price_cache.get(key)
    
    def get_latest_orderbook(self, platform: Platform, token_id: str) -> Optional[OrderbookUpdate]:
        """获取最新订单簿"""
        key = f"{platform.value}_{token_id}"
        return self.orderbook_cache.get(key)
    
    def get_all_prices(self) -> Dict[str, PriceUpdate]:
        """获取所有价格"""
        return self.price_cache.copy()
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            platform.value: client.get_stats()
            for platform, client in self.clients.items()
        }


# 全局单例
multi_platform_ws = MultiPlatformWebSocket()

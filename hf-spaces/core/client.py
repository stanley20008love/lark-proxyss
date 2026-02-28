"""
Polymarket API 客户端
"""
import asyncio
import json
from typing import Dict, List, Optional
from datetime import datetime
import aiohttp
import websockets
from loguru import logger

from config.settings import config


class PolymarketClient:
    """Polymarket CLOB API 客户端"""
    
    def __init__(self):
        self.http_url = config.CLOB_HTTP_URL
        self.ws_url = config.CLOB_WS_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws = None
    
    async def connect(self):
        """建立连接"""
        self.session = aiohttp.ClientSession()
        logger.info("✅ Polymarket 客户端已连接")
    
    async def close(self):
        """关闭连接"""
        if self.session:
            await self.session.close()
        if self.ws:
            await self.ws.close()
    
    # ==================== 市场数据 ====================
    
    async def get_markets(self, limit: int = 100) -> List[Dict]:
        """获取市场列表"""
        url = f"{self.http_url}/markets"
        async with self.session.get(url, params={"limit": limit}) as resp:
            data = await resp.json()
            return data.get("results", [])
    
    async def get_btc_15m_markets(self) -> List[Dict]:
        """获取 BTC 15分钟市场"""
        markets = await self.get_markets()
        btc_markets = [
            m for m in markets 
            if "btc" in m.get("question", "").lower() 
            and "15" in m.get("question", "").lower()
        ]
        return btc_markets
    
    async def get_orderbook(self, token_id: str) -> Dict:
        """获取订单簿"""
        url = f"{self.http_url}/book"
        async with self.session.get(url, params={"token_id": token_id}) as resp:
            return await resp.json()
    
    async def get_price(self, token_id: str) -> Dict:
        """获取当前价格"""
        url = f"{self.http_url}/price"
        async with self.session.get(url, params={"token_id": token_id}) as resp:
            return await resp.json()
    
    async def get_midpoint(self, token_id: str) -> float:
        """获取中间价"""
        data = await self.get_price(token_id)
        return float(data.get("price", 0.5))
    
    # ==================== WebSocket ====================
    
    async def connect_ws(self):
        """连接 WebSocket"""
        self.ws = await websockets.connect(self.ws_url)
        logger.info(f"✅ WebSocket 已连接")
    
    async def subscribe_orderbook(self, token_id: str):
        """订阅订单簿"""
        if not self.ws:
            await self.connect_ws()
        msg = {"type": "subscribe", "channel": "book", "token_id": token_id}
        await self.ws.send(json.dumps(msg))
    
    async def listen_ws(self):
        """监听 WebSocket 消息"""
        async for message in self.ws:
            yield json.loads(message)

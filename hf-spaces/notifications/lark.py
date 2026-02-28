"""
飞书通知模块
"""
from typing import Dict, Optional
from datetime import datetime
import httpx
from loguru import logger

from config.settings import config


class LarkNotifier:
    """飞书消息通知"""
    
    def __init__(self):
        self.app_id = config.lark.APP_ID
        self.app_secret = config.lark.APP_SECRET
        self.api_url = config.lark.API_URL
        self._token_cache = {"token": None, "expire": 0}
    
    async def _get_token(self) -> Optional[str]:
        """获取访问令牌"""
        import time
        now = time.time()
        
        if self._token_cache["token"] and now < self._token_cache["expire"]:
            return self._token_cache["token"]
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.api_url}/auth/v3/tenant_access_token/internal",
                    json={"app_id": self.app_id, "app_secret": self.app_secret}
                )
                data = resp.json()
                if data.get("code") == 0:
                    self._token_cache["token"] = data["tenant_access_token"]
                    self._token_cache["expire"] = now + 7000
                    return self._token_cache["token"]
        except Exception as e:
            logger.error(f"获取 Token 失败: {e}")
        return None
    
    async def send_to_chat(self, chat_id: str, message: str) -> bool:
        """发送消息到群聊"""
        token = await self._get_token()
        if not token:
            return False
        
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self.api_url}/im/v1/messages?receive_id_type=chat_id",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "receive_id": chat_id,
                        "msg_type": "text",
                        "content": f'{{"text": "{message}"}}'
                    }
                )
                result = resp.json()
                return result.get("code") == 0
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False
    
    # ==================== 预设消息 ====================
    
    async def notify_trade_signal(self, chat_id: str, signal: Dict):
        """通知交易信号"""
        message = f"""🚨 交易信号

📊 方向: {signal.get('direction', 'N/A')}
💪 强度: {signal.get('strength', 0):.1%}
⏰ {datetime.now().strftime('%H:%M:%S')}"""
        await self.send_to_chat(chat_id, message)
    
    async def notify_flash_crash(self, chat_id: str, event: Dict):
        """通知 Flash Crash"""
        message = f"""🚨 Flash Crash 检测！

📉 变化: {event.get('drop_pct', 0):.2%}
💰 价格: {event.get('price_after', 0):.4f}
⏰ {datetime.now().strftime('%H:%M:%S')}"""
        await self.send_to_chat(chat_id, message)
    
    async def notify_trade_executed(self, chat_id: str, trade: Dict):
        """通知交易执行"""
        message = f"""✅ 交易已执行

{trade.get('side', 'N/A')} @ {trade.get('price', 0):.4f}
📦 数量: {trade.get('size', 0):.2f}
📝 模拟: {'是' if trade.get('simulation') else '否'}
⏰ {datetime.now().strftime('%H:%M:%S')}"""
        await self.send_to_chat(chat_id, message)
    
    async def notify_risk_alert(self, chat_id: str, alert: Dict):
        """通知风险警告"""
        message = f"""⚠️ 风险警告

等级: {alert.get('level', 'N/A')}
信息: {alert.get('message', 'N/A')}
操作: {alert.get('action', 'N/A')}
⏰ {datetime.now().strftime('%H:%M:%S')}"""
        await self.send_to_chat(chat_id, message)
    
    async def notify_daily_summary(self, chat_id: str, summary: Dict):
        """发送每日摘要"""
        message = f"""📊 每日摘要

💰 盈亏: {summary.get('daily_pnl', 0):.2f}
📝 交易: {summary.get('trades', 0)}
📊 风险: {summary.get('risk_level', 'N/A')}
⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}"""
        await self.send_to_chat(chat_id, message)
    
    async def notify_backtest_result(self, chat_id: str, result: Dict):
        """通知回测结果"""
        message = f"""📈 回测结果

💰 初始: {result.get('initial_capital', 0):.0f}
💰 最终: {result.get('final_capital', 0):.0f}
📊 盈亏: {result.get('total_pnl', 0):.2f}
📝 交易: {result.get('total_trades', 0)}
🎯 胜率: {result.get('win_rate', 0):.1%}
📉 回撤: {result.get('max_drawdown', 0):.2%}
⏰ {datetime.now().strftime('%Y-%m-%d')}"""
        await self.send_to_chat(chat_id, message)

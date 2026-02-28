"""
安全监控模块 (Security Monitor)

实时监控安全状态并发送告警:
1. 异常交易检测
2. 大额资金变动
3. 系统访问监控
4. 多渠道告警
"""
import os
import asyncio
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertType(Enum):
    """告警类型"""
    LARGE_TRANSACTION = "large_transaction"
    HIGH_FREQUENCY = "high_frequency"
    LOSS_THRESHOLD = "loss_threshold"
    CIRCUIT_BREAKER = "circuit_breaker"
    UNUSUAL_ACTIVITY = "unusual_activity"
    FUND_OUTFLOW = "fund_outflow"
    API_ERROR = "api_error"
    SYSTEM_ERROR = "system_error"


@dataclass
class SecurityAlert:
    """安全告警"""
    alert_id: str
    alert_type: AlertType
    level: AlertLevel
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False


class AlertChannel:
    """告警渠道基类"""
    
    async def send(self, alert: SecurityAlert) -> bool:
        """发送告警"""
        raise NotImplementedError


class LarkAlertChannel(AlertChannel):
    """飞书告警渠道"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("LARK_WEBHOOK_URL")
    
    async def send(self, alert: SecurityAlert) -> bool:
        """发送飞书告警"""
        if not self.webhook_url:
            logger.warning("飞书 Webhook 未配置")
            return False
        
        # 构建飞书卡片消息
        color_map = {
            AlertLevel.INFO: "blue",
            AlertLevel.WARNING: "yellow",
            AlertLevel.CRITICAL: "red",
            AlertLevel.EMERGENCY: "red"
        }
        
        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"🚨 {alert.title}"},
                    "template": color_map.get(alert.level, "blue")
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "plain_text", "content": alert.message}},
                    {"tag": "div", "text": {"tag": "plain_text", "content": f"时间: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"}},
                    {"tag": "div", "text": {"tag": "plain_text", "content": f"级别: {alert.level.value}"}}
                ]
            }
        }
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=card) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"飞书告警发送失败: {e}")
            return False


class TelegramAlertChannel(AlertChannel):
    """Telegram 告警渠道"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    
    async def send(self, alert: SecurityAlert) -> bool:
        """发送 Telegram 告警"""
        if not self.bot_token or not self.chat_id:
            return False
        
        emoji_map = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.EMERGENCY: "🆘"
        }
        
        text = f"""
{emoji_map.get(alert.level, '📢')} *{alert.title}*

{alert.message}

级别: `{alert.level.value}`
时间: `{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}`
        """.strip()
        
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram 告警发送失败: {e}")
            return False


class LogAlertChannel(AlertChannel):
    """日志告警渠道"""
    
    async def send(self, alert: SecurityAlert) -> bool:
        """记录日志"""
        level_map = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.CRITICAL,
            AlertLevel.EMERGENCY: logging.CRITICAL
        }
        
        logger.log(
            level_map.get(alert.level, logging.INFO),
            f"[{alert.alert_type.value}] {alert.title}: {alert.message}"
        )
        return True


class SecurityMonitor:
    """
    安全监控器
    
    监控所有安全相关事件
    """
    
    def __init__(self):
        self.alerts: List[SecurityAlert] = []
        self.channels: List[AlertChannel] = []
        self._alert_count = 0
        
        # 添加默认渠道
        self.channels.append(LogAlertChannel())
        
        # 监控规则
        self.thresholds = {
            "large_transaction_usd": 100.0,
            "high_frequency_per_minute": 20,
            "loss_warning_pct": 0.03,
            "loss_critical_pct": 0.05,
            "outflow_warning_pct": 0.10,
        }
        
        # 从环境变量加载配置
        self._load_config()
    
    def _load_config(self):
        """加载配置"""
        self.thresholds["large_transaction_usd"] = float(
            os.getenv("ALERT_LARGE_TRANSACTION_USD", "100")
        )
        self.thresholds["loss_warning_pct"] = float(
            os.getenv("ALERT_LOSS_WARNING_PCT", "0.03")
        )
        self.thresholds["loss_critical_pct"] = float(
            os.getenv("ALERT_LOSS_CRITICAL_PCT", "0.05")
        )
    
    def add_channel(self, channel: AlertChannel):
        """添加告警渠道"""
        self.channels.append(channel)
    
    async def send_alert(self, alert: SecurityAlert):
        """发送告警到所有渠道"""
        self.alerts.append(alert)
        self._alert_count += 1
        
        # 并行发送到所有渠道
        results = await asyncio.gather(
            *[channel.send(alert) for channel in self.channels],
            return_exceptions=True
        )
        
        success_count = sum(1 for r in results if r is True)
        logger.info(f"告警已发送到 {success_count}/{len(self.channels)} 个渠道")
    
    def create_alert(
        self,
        alert_type: AlertType,
        level: AlertLevel,
        title: str,
        message: str,
        details: Dict = None
    ) -> SecurityAlert:
        """创建告警"""
        self._alert_count += 1
        return SecurityAlert(
            alert_id=f"alert_{self._alert_count}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            alert_type=alert_type,
            level=level,
            title=title,
            message=message,
            details=details or {}
        )
    
    async def check_transaction(self, amount: float, balance: float, daily_pnl: float) -> List[SecurityAlert]:
        """检查交易异常"""
        alerts = []
        
        # 大额交易检查
        if amount >= self.thresholds["large_transaction_usd"]:
            alert = self.create_alert(
                AlertType.LARGE_TRANSACTION,
                AlertLevel.WARNING,
                "大额交易告警",
                f"检测到大额交易: ${amount:.2f}",
                {"amount": amount, "balance": balance}
            )
            alerts.append(alert)
        
        # 亏损告警
        if balance > 0:
            loss_pct = abs(daily_pnl) / balance
            
            if loss_pct >= self.thresholds["loss_critical_pct"]:
                alert = self.create_alert(
                    AlertType.LOSS_THRESHOLD,
                    AlertLevel.CRITICAL,
                    "严重亏损告警",
                    f"每日亏损已达 {loss_pct:.1%}，请立即检查！",
                    {"loss_pct": loss_pct, "daily_pnl": daily_pnl}
                )
                alerts.append(alert)
            elif loss_pct >= self.thresholds["loss_warning_pct"]:
                alert = self.create_alert(
                    AlertType.LOSS_THRESHOLD,
                    AlertLevel.WARNING,
                    "亏损预警",
                    f"每日亏损已达 {loss_pct:.1%}，请注意风险",
                    {"loss_pct": loss_pct, "daily_pnl": daily_pnl}
                )
                alerts.append(alert)
        
        # 发送告警
        for alert in alerts:
            await self.send_alert(alert)
        
        return alerts
    
    async def check_fund_outflow(self, outflow_amount: float, total_balance: float) -> Optional[SecurityAlert]:
        """检查资金流出"""
        if total_balance <= 0:
            return None
        
        outflow_pct = outflow_amount / total_balance
        
        if outflow_pct >= self.thresholds["outflow_warning_pct"]:
            alert = self.create_alert(
                AlertType.FUND_OUTFLOW,
                AlertLevel.CRITICAL,
                "资金流出告警",
                f"检测到大额资金流出: ${outflow_amount:.2f} ({outflow_pct:.1%})",
                {"outflow_amount": outflow_amount, "outflow_pct": outflow_pct}
            )
            await self.send_alert(alert)
            return alert
        
        return None
    
    async def check_high_frequency(self, trades_per_minute: int) -> Optional[SecurityAlert]:
        """检查高频交易"""
        if trades_per_minute >= self.thresholds["high_frequency_per_minute"]:
            alert = self.create_alert(
                AlertType.HIGH_FREQUENCY,
                AlertLevel.WARNING,
                "高频交易告警",
                f"交易频率异常: {trades_per_minute} 笔/分钟",
                {"trades_per_minute": trades_per_minute}
            )
            await self.send_alert(alert)
            return alert
        
        return None
    
    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """获取最近告警"""
        return [
            {
                "alert_id": a.alert_id,
                "type": a.alert_type.value,
                "level": a.level.value,
                "title": a.title,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "acknowledged": a.acknowledged
            }
            for a in self.alerts[-limit:]
        ]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            "total_alerts": len(self.alerts),
            "unacknowledged": sum(1 for a in self.alerts if not a.acknowledged),
            "by_level": {
                level.value: sum(1 for a in self.alerts if a.level == level)
                for level in AlertLevel
            },
            "by_type": {
                atype.value: sum(1 for a in self.alerts if a.alert_type == atype)
                for atype in AlertType
            },
            "channels": len(self.channels)
        }


# 全局监控实例
security_monitor = SecurityMonitor()

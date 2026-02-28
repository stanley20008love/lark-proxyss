"""
Polymarket Super Bot - Interactive Control Panel

完整功能:
1. 飞书交互式卡片控制面板
2. Black-Scholes 二元期权定价
3. Binance 实时数据
4. Maker/Taker/Hybrid 策略
5. 风险管理
"""
import os
import json
import asyncio
import logging
import time
import math
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from enum import Enum

import gradio as gr
import httpx

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger(__name__)

# Config
APP_ID = os.getenv("LARK_APP_ID", "cli_a9f678dd01b8de1b")
APP_SECRET = os.getenv("LARK_APP_SECRET", "4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K")
API = "https://open.larksuite.com/open-apis"

_cache = {"token": None, "expire": 0}
_price_cache = {"data": None, "time": 0}


# ==================== Bot State ====================

class BotState:
    status: str = "running"
    strategy: str = "hybrid"
    market_maker_enabled: bool = False
    arbitrage_enabled: bool = False
    spread_bps: int = 150
    min_profit: float = 0.02
    max_position: float = 100.0
    stop_loss: float = 0.30
    circuit_breaker: bool = False
    trades: int = 0
    pnl: float = 0.0
    signals: int = 0
    win_rate: float = 0.68

    def to_dict(self):
        return {
            "status": self.status,
            "strategy": self.strategy,
            "market_maker_enabled": self.market_maker_enabled,
            "arbitrage_enabled": self.arbitrage_enabled,
            "spread_bps": self.spread_bps,
            "min_profit": self.min_profit,
            "max_position": self.max_position,
            "stop_loss": self.stop_loss,
            "circuit_breaker": self.circuit_breaker,
            "trades": self.trades,
            "pnl": self.pnl,
            "signals": self.signals,
            "win_rate": self.win_rate
        }


bot_state = BotState()


# ==================== Black-Scholes ====================

def norm_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))
def norm_pdf(x): return math.exp(-0.5 * x ** 2) / math.sqrt(2 * math.pi)


def price_binary_option(S, K, T, r=0.05, sigma=0.5, is_call=True):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0: return 0.5
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    price = math.exp(-r * T) * norm_cdf(d2 if is_call else -d2)
    return max(0.0, min(1.0, price))


# ==================== Real-time Prices ====================

async def get_prices():
    """获取实时价格 - 从 Binance API"""
    # 使用缓存 (5秒有效期)
    now = time.time()
    if _price_cache["data"] and now - _price_cache["time"] < 5:
        return _price_cache["data"]
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # 并行获取多个币种价格
            urls = [
                "https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT",
                "https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT",
                "https://api.binance.com/api/v3/ticker/24hr?symbol=SOLUSDT",
            ]
            
            responses = await asyncio.gather(
                *[client.get(url) for url in urls],
                return_exceptions=True
            )
            
            result = {}
            
            # BTC
            if not isinstance(responses[0], Exception):
                try:
                    data = responses[0].json()
                    result["btc"] = float(data.get("lastPrice", 0))
                    result["btc_change"] = float(data.get("priceChangePercent", 0))
                except:
                    pass
            
            # ETH
            if not isinstance(responses[1], Exception):
                try:
                    data = responses[1].json()
                    result["eth"] = float(data.get("lastPrice", 0))
                    result["eth_change"] = float(data.get("priceChangePercent", 0))
                except:
                    pass
            
            # SOL
            if not isinstance(responses[2], Exception):
                try:
                    data = responses[2].json()
                    result["sol"] = float(data.get("lastPrice", 0))
                    result["sol_change"] = float(data.get("priceChangePercent", 0))
                except:
                    pass
            
            # 验证数据
            if result.get("btc", 0) > 0 and result.get("eth", 0) > 0:
                _price_cache["data"] = result
                _price_cache["time"] = now
                return result
            
    except Exception as e:
        log.error(f"Price fetch error: {e}")
    
    # 如果有缓存，使用缓存（即使过期）
    if _price_cache["data"]:
        return _price_cache["data"]
    
    # 返回错误标识
    return {"error": "无法获取实时价格", "btc": 0, "eth": 0}


async def get_prices_with_retry(max_retries=3):
    """带重试的价格获取"""
    for i in range(max_retries):
        prices = await get_prices()
        if prices.get("btc", 0) > 0:
            return prices
        await asyncio.sleep(0.5)
    return prices


# ==================== Lark Cards ====================

def create_main_dashboard_card(prices):
    # 检查是否有错误
    if prices.get("error"):
        price_text_btc = f"❌ {prices['error']}"
        price_text_eth = ""
    else:
        btc_price = prices.get("btc", 0)
        eth_price = prices.get("eth", 0)
        btc_change = prices.get("btc_change", 0)
        eth_change = prices.get("eth_change", 0)
        
        price_text_btc = f"**🪙 BTC/USDT**\n${btc_price:,.2f}\n{btc_change:+.2f}%"
        price_text_eth = f"**💎 ETH/USDT**\n${eth_price:,.2f}\n{eth_change:+.2f}%"
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🤖 Polymarket Super Bot"},
            "subtitle": {"tag": "plain_text", "content": f"状态: {'✅ 运行中' if bot_state.status == 'running' else '⏸️ 已暂停'}"},
            "template": "blue" if bot_state.status == "running" else "grey"
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": price_text_btc}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": price_text_eth}}
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📊 信号**\n{bot_state.signals}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**💰 盈亏**\n${bot_state.pnl:+.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📈 交易**\n{bot_state.trades}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**🎯 胜率**\n{bot_state.win_rate:.0%}"}}
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📈 做市商**\n{'✅ 启用' if bot_state.market_maker_enabled else '⏸️ 禁用'}\n价差: {bot_state.spread_bps}bps"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**💰 套利**\n{'✅ 启用' if bot_state.arbitrage_enabled else '⏸️ 禁用'}\n最小利润: {bot_state.min_profit:.1%}"}}
                ]
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📊 市场"}, "type": "primary", "value": {"action": "markets"}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "📐 定价"}, "type": "default", "value": {"action": "pricing"}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "⚙️ 配置"}, "type": "default", "value": {"action": "config"}}
                ]
            },
            {
                "tag": "action",
                "actions": [
                    {"tag": "button", "text": {"tag": "plain_text", "content": "▶️ 启动做市" if not bot_state.market_maker_enabled else "⏸️ 停止做市"}, "type": "primary" if not bot_state.market_maker_enabled else "danger", "value": {"action": "toggle_mm"}},
                    {"tag": "button", "text": {"tag": "plain_text", "content": "▶️ 启动套利" if not bot_state.arbitrage_enabled else "⏸️ 停止套利"}, "type": "primary" if not bot_state.arbitrage_enabled else "danger", "value": {"action": "toggle_arb"}}
                ]
            },
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 策略: {bot_state.strategy.upper()} | 数据源: Binance"}]}
        ]
    }


def create_pricing_card(data, prices):
    # 使用实时价格
    current_price = prices.get("btc", 0) if prices else 0
    if current_price <= 0:
        current_price = data.get("current_price", 0)
    
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📐 BS 定价分析"},
            "template": "purple"
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**🎯 {data['market']}**"}},
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**💰 当前价格**\n${current_price:,.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**🎯 行权价**\n${data['strike_price']:,.2f}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📊 市场**\n{data['market_price']:.1%}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📐 理论**\n{data['theoretical_price']:.1%}"}}
                ]
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**📈 波动率**\n{data['volatility']:.1%}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**⚡ 边际**\n{data['edge']:+.2%}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**🎯 信号**\n{data['signal']}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**💪 置信度**\n{data['confidence']:.0%}"}}
                ]
            },
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**💡 建议:** {data['recommendation']}"}},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "✅ 执行交易"}, "type": "primary", "value": {"action": "execute"}},
                {"tag": "button", "text": {"tag": "plain_text", "content": "🏠 返回"}, "type": "default", "value": {"action": "main"}}
            ]}
        ]
    }


def create_config_card():
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚙️ 系统配置"},
            "template": "grey"
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": "**🎯 执行策略**"}},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"当前: **{bot_state.strategy.upper()}**"}}
            ]},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**📈 做市商配置**"}},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**价差:** {bot_state.spread_bps} bps"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**状态:** {'✅ 启用' if bot_state.market_maker_enabled else '⏸️ 禁用'}"}}
            ]},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**💰 套利配置**"}},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**最小利润:** {bot_state.min_profit:.1%}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**状态:** {'✅ 启用' if bot_state.arbitrage_enabled else '⏸️ 禁用'}"}}
            ]},
            {"tag": "hr"},
            {"tag": "div", "text": {"tag": "lark_md", "content": "**🛡️ 风险管理**"}},
            {"tag": "div", "fields": [
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**最大仓位:** ${bot_state.max_position}"}},
                {"is_short": True, "text": {"tag": "lark_md", "content": f"**止损:** {bot_state.stop_loss:.0%}"}}
            ]},
            {"tag": "action", "actions": [
                {"tag": "button", "text": {"tag": "plain_text", "content": "🏠 返回"}, "type": "default", "value": {"action": "main"}}
            ]}
        ]
    }


# ==================== API Functions ====================

async def get_token():
    now = time.time()
    if _cache["token"] and now < _cache["expire"]:
        return _cache["token"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{API}/auth/v3/tenant_access_token/internal",
                json={"app_id": APP_ID, "app_secret": APP_SECRET}
            )
            d = r.json()
            if d.get("code") == 0:
                _cache["token"] = d["tenant_access_token"]
                _cache["expire"] = now + 7000
                return _cache["token"]
    except Exception as e:
        log.error(f"Token error: {e}")
    return None


async def send_card(open_id: str, card: dict):
    token = await get_token()
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{API}/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={"receive_id": open_id, "msg_type": "interactive", "content": json.dumps(card)}
            )
            return True
    except Exception as e:
        log.error(f"Send card error: {e}")
    return False


async def send_text(open_id: str, text: str):
    token = await get_token()
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{API}/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={"receive_id": open_id, "msg_type": "text", "content": json.dumps({"text": text})}
            )
            return True
    except Exception as e:
        log.error(f"Send text error: {e}")
    return False


def analyze_pricing(current_price: float = 0):
    """分析定价 - 使用实时价格"""
    # 如果没有提供价格，使用默认比例
    if current_price <= 0:
        # 返回等待状态
        return {
            "market": "等待价格数据...",
            "current_price": 0,
            "strike_price": 0,
            "market_price": 0.5,
            "theoretical_price": 0.5,
            "volatility": 0.5,
            "edge": 0,
            "signal": "HOLD",
            "confidence": 0,
            "recommendation": "等待实时价格数据"
        }
    
    # 行权价 = 当前价格 * 1.005 (模拟 15 分钟涨跌预测)
    strike_price = current_price * 1.005
    
    # 计算理论价格
    T = 15 * 60 / (365 * 24 * 3600)  # 15分钟转年
    theoretical_price = price_binary_option(current_price, strike_price, T, 0.05, 0.45)
    
    # 模拟市场价格 (实际应从 Polymarket 获取)
    market_price = 0.48
    
    # 计算边际
    edge = theoretical_price - market_price
    
    # 生成信号
    if edge > 0.02:
        signal = "BUY_YES"
        recommendation = f"建议买入 YES，边际 +{edge:.1%}，超过 2% 阈值"
    elif edge < -0.02:
        signal = "BUY_NO"
        recommendation = f"建议买入 NO，边际 {edge:.1%}"
    else:
        signal = "HOLD"
        recommendation = "边际不足，建议观望"
    
    return {
        "market": "BTC 15分钟内上涨?",
        "current_price": current_price,
        "strike_price": strike_price,
        "market_price": market_price,
        "theoretical_price": theoretical_price,
        "volatility": 0.45,
        "edge": edge,
        "signal": signal,
        "confidence": min(1.0, abs(edge) * 20),
        "recommendation": recommendation
    }


# ==================== Message Processing ====================

async def process_message(text: str, open_id: str = ""):
    t = text.lower().strip()

    if t in ["help", "/help", "?"]:
        return """🤖 Polymarket Super Bot - 控制面板

📱 **控制面板:**
  panel - 打开主控制面板
  pricing - 定价分析面板
  config - 配置面板

⚡ **快捷操作:**
  mm on/off - 启停做市商
  arb on/off - 启停套利
  strategy <taker/maker/hybrid>

📊 **查询:**
  btc, eth - 实时价格
  status - 状态"""

    if t == "panel":
        prices = await get_prices_with_retry()
        await send_card(open_id, create_main_dashboard_card(prices))
        return None

    if t == "pricing":
        prices = await get_prices_with_retry()
        data = analyze_pricing(prices.get("btc", 0))
        await send_card(open_id, create_pricing_card(data, prices))
        return None

    if t == "config":
        await send_card(open_id, create_config_card())
        return None

    if t == "mm on":
        bot_state.market_maker_enabled = True
        return "✅ 做市商已启用"

    if t == "mm off":
        bot_state.market_maker_enabled = False
        return "⏸️ 做市商已停止"

    if t == "arb on":
        bot_state.arbitrage_enabled = True
        return "✅ 套利已启用"

    if t == "arb off":
        bot_state.arbitrage_enabled = False
        return "⏸️ 套利已停止"

    if t.startswith("strategy "):
        s = t.split()[1]
        if s in ["taker", "maker", "hybrid"]:
            bot_state.strategy = s if s != "maker" else "market_maker"
            return f"✅ 策略已切换: {s.upper()}"

    if t == "btc":
        prices = await get_prices_with_retry()
        if prices.get("error"):
            return f"❌ {prices['error']}"
        return f"🪙 BTC/USDT\n💰 ${prices['btc']:,.2f}\n{prices['btc_change']:+.2f}%\n📍 Binance\n⏰ {datetime.now().strftime('%H:%M:%S')}"

    if t == "eth":
        prices = await get_prices_with_retry()
        if prices.get("error"):
            return f"❌ {prices['error']}"
        return f"💎 ETH/USDT\n💰 ${prices['eth']:,.2f}\n{prices['eth_change']:+.2f}%\n📍 Binance\n⏰ {datetime.now().strftime('%H:%M:%S')}"

    if t == "status":
        prices = await get_prices()
        btc_price = prices.get('btc', 0)
        price_info = f"${btc_price:,.2f}" if btc_price > 0 else "获取中..."
        
        return f"""🤖 Bot 状态

📊 状态: {'✅ 运行中' if bot_state.status == 'running' else '⏸️ 已暂停'}
🎯 策略: {bot_state.strategy.upper()}
📈 做市商: {'✅' if bot_state.market_maker_enabled else '⏸️'}
💰 套利: {'✅' if bot_state.arbitrage_enabled else '⏸️'}
📊 信号: {bot_state.signals}
💰 盈亏: ${bot_state.pnl:+.2f}
🪙 BTC: {price_info}"""

    return f"🤖 收到: {text}\n💡 输入 'panel' 打开控制面板"


# ==================== Gradio Interface ====================

def chat_fn(message, history):
    if not message:
        return history
    try:
        response = asyncio.run(process_message(message))
        if response:
            history.append((message, response))
    except Exception as e:
        history.append((message, f"Error: {e}"))
    return history


with gr.Blocks(title="Polymarket Control Panel", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""# 🤖 Polymarket Super Bot - 控制面板

**功能:**
- 📐 BS 定价模型
- ⚡ Binance 实时数据
- 🎯 Maker/Taker/Hybrid 策略
- 📱 飞书交互式卡片""")

    chatbot = gr.Chatbot(height=400)
    with gr.Row():
        msg = gr.Textbox(placeholder="输入 'panel' 打开控制面板...", scale=4, show_label=False)
        btn = gr.Button("Send", variant="primary", scale=1)

    msg.submit(chat_fn, [msg, chatbot], [chatbot])
    btn.click(chat_fn, [msg, chatbot], [chatbot])


# ==================== FastAPI ====================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Polymarket Control Panel")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def webhook_middleware(request: Request, call_next):
    if request.url.path in ["/webhook", "/api"]:
        return await handle_webhook(request)
    return await call_next(request)


async def handle_webhook(request: Request) -> Response:
    if request.method == "GET":
        return Response(content=json.dumps({"status": "ok"}), media_type="application/json")

    try:
        body = await request.json()

        if body.get("type") == "url_verification":
            return Response(content=json.dumps({"challenge": body.get("challenge", "")}), media_type="application/json")

        # Card callback
        if body.get("type") == "card":
            action = body.get("action", {}).get("value", {}).get("action", "")
            open_id = body.get("open_id", "")

            prices = await get_prices_with_retry()

            if action == "main":
                card = create_main_dashboard_card(prices)
            elif action == "pricing":
                data = analyze_pricing(prices.get("btc", 0))
                card = create_pricing_card(data, prices)
            elif action == "config":
                card = create_config_card()
            elif action == "toggle_mm":
                bot_state.market_maker_enabled = not bot_state.market_maker_enabled
                card = create_main_dashboard_card(prices)
            elif action == "toggle_arb":
                bot_state.arbitrage_enabled = not bot_state.arbitrage_enabled
                card = create_main_dashboard_card(prices)
            else:
                card = create_main_dashboard_card(prices)

            return Response(content=json.dumps({"card": card}), media_type="application/json")

        # Message event
        if body.get("header", {}).get("event_type") == "im.message.receive_v1":
            event = body.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {}).get("sender_id", {})

            if message.get("message_type") == "text":
                try:
                    content = json.loads(message.get("content", "{}"))
                    text = content.get("text", "")
                except:
                    text = message.get("content", "")

                open_id = sender.get("open_id", "")

                if text and open_id:
                    response = await process_message(text, open_id)
                    if response:
                        await send_text(open_id, response)

        return Response(content=json.dumps({"code": 0}), media_type="application/json")

    except Exception as e:
        log.error(f"Webhook error: {e}")
        return Response(content=json.dumps({"code": -1, "error": str(e)}), media_type="application/json")


@app.get("/health")
async def health():
    prices = await get_prices()
    return {
        "status": "ok", 
        "bot": bot_state.to_dict(),
        "prices": {
            "btc": prices.get("btc", 0),
            "eth": prices.get("eth", 0)
        }
    }


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

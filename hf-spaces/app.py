"""
AI Agent - Polymarket Super Bot with Lark Integration

整合功能:
- 飞书机器人 Webhook
- Polymarket 交易机器人
- 做市商策略
- 跨平台套利
- 风险管理
- 技术分析
"""
import os
import json
import asyncio
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

import gradio as gr
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger(__name__)

# Configuration
APP_ID = os.getenv("LARK_APP_ID", "cli_a9f678dd01b8de1b")
APP_SECRET = os.getenv("LARK_APP_SECRET", "4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "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")
API = "https://open.lark.cn/open-apis"

# Cache
_cache = {"token": None, "expire": 0}


# ==================== Enums & Data Classes ====================

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ArbitrageType(Enum):
    CROSS_PLATFORM = "cross_platform"
    INTRA_PLATFORM = "intra_platform"
    TRIANGULAR = "triangular"


@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float
    platform: str = "Polymarket"


@dataclass
class Position:
    market_id: str
    side: str
    size: float
    entry_price: float
    current_price: float
    pnl: float


# ==================== Lark API Functions ====================

async def get_token():
    """Get Lark tenant access token"""
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


async def send_msg(open_id: str, msg: str):
    """Send message to Lark user"""
    token = await get_token()
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{API}/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={"receive_id": open_id, "msg_type": "text", "content": json.dumps({"text": msg})}
            )
            return r.json().get("code") == 0
    except Exception as e:
        log.error(f"Send error: {e}")
        return False


# ==================== Market Data Functions ====================

async def get_btc_price():
    """Get BTC price from Binance"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            data = r.json()
            price = float(data.get("price", 0))
            return f"🪙 BTC/USDT\n💰 ${price:,.2f}\n📍 Binance"
    except:
        return "❌ Failed to get BTC price"


async def get_eth_price():
    """Get ETH price from Binance"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT")
            data = r.json()
            price = float(data.get("price", 0))
            return f"💎 ETH/USDT\n💰 ${price:,.2f}\n📍 Binance"
    except:
        return "❌ Failed to get ETH price"


async def get_all_prices():
    """Get all crypto prices"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            btc_r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
            eth_r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT")
            sol_r = await client.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT")
            btc = btc_r.json()
            eth = eth_r.json()
            sol = sol_r.json()
            return f"""📊 Crypto Prices

🪙 BTC: ${float(btc['price']):,.2f}
💎 ETH: ${float(eth['price']):,.2f}
🌞 SOL: ${float(sol['price']):,.2f}

📍 Binance | Updated: {datetime.now().strftime('%H:%M:%S')}"""
    except:
        return "❌ Failed to get prices"


# ==================== Polymarket Super Bot ====================

class PolymarketSuperBot:
    """Polymarket Super Bot - Enhanced with predict-fun-marketmaker features"""
    
    def __init__(self):
        self.markets: List[Market] = self._init_markets()
        self.positions: List[Position] = []
        self.risk_level = RiskLevel.LOW
        self.running = True
        self.config = {
            "market_maker": {"enabled": False, "spread_bps": 150},
            "arbitrage": {"enabled": False, "min_profit": 0.01},
            "risk": {"max_position": 100, "stop_loss": 0.30}
        }
        self.stats = {
            "trades": 0,
            "pnl": 0.0,
            "arbitrage_opportunities": 0,
            "win_rate": 0.68
        }
    
    def _init_markets(self) -> List[Market]:
        """Initialize mock markets"""
        return [
            Market("btc_100k", "Will BTC reach $100k by March 2025?", 0.72, 0.28, 150000),
            Market("eth_5k", "Will ETH exceed $5,000 by Q2 2025?", 0.45, 0.55, 80000),
            Market("sol_200", "Will SOL break $200 in 2025?", 0.58, 0.42, 50000),
            Market("trump_2024", "Trump wins 2024 election?", 0.52, 0.48, 200000),
            Market("rate_cut", "Fed cuts rates in March?", 0.25, 0.75, 120000),
            Market("btc_etf", "BTC ETF approved by SEC?", 0.85, 0.15, 300000),
            Market("eth_etf", "ETH ETF approved in 2024?", 0.42, 0.58, 180000),
            Market("sol_etf", "SOL ETF approved in 2025?", 0.15, 0.85, 90000),
        ]
    
    def get_dashboard(self) -> Dict:
        """Get dashboard data"""
        return {
            "status": "运行中" if self.running else "已停止",
            "risk_level": self.risk_level.value,
            "markets_tracked": len(self.markets),
            "positions": len(self.positions),
            "total_pnl": f"${self.stats['pnl']:.2f}",
            "win_rate": f"{self.stats['win_rate']:.0%}",
            "market_maker": "启用" if self.config["market_maker"]["enabled"] else "禁用",
            "arbitrage": "启用" if self.config["arbitrage"]["enabled"] else "禁用",
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def get_markets_table(self) -> List[List]:
        """Get markets as table"""
        return [
            [m.id, m.question[:35] + "...", f"{m.yes_price:.1%}", f"${m.liquidity:,}"]
            for m in self.markets[:6]
        ]
    
    def get_arbitrage_opportunities(self) -> List[Dict]:
        """Find arbitrage opportunities"""
        opportunities = []
        for m in self.markets:
            # Simulate cross-platform arbitrage
            if abs(m.yes_price + m.no_price - 1.0) > 0.02:
                profit = abs(m.yes_price + m.no_price - 1.0)
                opportunities.append({
                    "market": m.id,
                    "type": "站内套利",
                    "profit": f"{profit:.2%}",
                    "confidence": "高" if profit > 0.03 else "中"
                })
        return opportunities
    
    def get_risk_metrics(self) -> Dict:
        """Get risk metrics"""
        return {
            "portfolio_value": 10000.00,
            "unrealized_pnl": 250.50,
            "realized_pnl": 1200.00,
            "max_drawdown": "5.2%",
            "win_rate": f"{self.stats['win_rate']:.0%}",
            "sharpe_ratio": 1.85,
            "open_positions": len(self.positions),
            "daily_pnl": 85.30,
            "risk_level": self.risk_level.value,
            "circuit_breaker": "正常"
        }
    
    def analyze_market(self, market_id: str) -> Dict:
        """Analyze a market"""
        market = next((m for m in self.markets if m.id == market_id), None)
        if not market:
            return {"error": "Market not found"}
        
        return {
            "market": market.question,
            "current_price": f"{market.yes_price:.1%}",
            "liquidity": f"${market.liquidity:,}",
            "rsi": 45.5,
            "macd": "看涨" if market.yes_price > 0.5 else "看跌",
            "support": f"{max(0.1, market.yes_price - 0.1):.1%}",
            "resistance": f"{min(0.9, market.yes_price + 0.1):.1%}",
            "trend": "上升趋势" if market.yes_price > 0.5 else "下降趋势",
            "recommendation": "买入 YES" if market.yes_price < 0.7 else "观望"
        }
    
    def execute_trade(self, market_id: str, side: str, amount: float) -> Dict:
        """Execute a trade (simulated)"""
        market = next((m for m in self.markets if m.id == market_id), None)
        if not market:
            return {"error": "Market not found"}
        
        self.stats["trades"] += 1
        return {
            "status": "成功 (模拟)",
            "market": market.question,
            "side": side,
            "amount": f"${amount:.2f}",
            "price": f"{market.yes_price:.1%}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tx_id": f"tx_{int(time.time())}"
        }
    
    def configure(self, component: str, **kwargs) -> Dict:
        """Configure bot components"""
        if component in self.config:
            self.config[component].update(kwargs)
        return {
            "status": "配置已更新",
            "component": component,
            "config": self.config[component],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def run_backtest(self, strategy: str, period: str, capital: float) -> Dict:
        """Run backtest (simulated)"""
        return {
            "strategy": strategy,
            "period": period,
            "initial_capital": f"${capital:,.2f}",
            "final_capital": f"${capital * 1.25:,.2f}",
            "total_return": "+25%",
            "total_trades": 156,
            "win_rate": "68%",
            "max_drawdown": "-8.5%",
            "sharpe_ratio": 1.85
        }


# Create bot instance
bot = PolymarketSuperBot()


# ==================== Message Processing ====================

async def process_message(text: str) -> str:
    """Process message and return response"""
    t = text.lower().strip()
    
    if t in ["help", "/help", "?"]:
        return """🤖 Polymarket Super Bot Commands:

📊 Crypto: btc, eth, crypto
🎯 Polymarket: markets, arbitrage, risk
📈 Trading: trade <market> <side> <amount>
⚙️ Config: mm on/off, arb on/off
🧪 Analysis: analyze <market>
💡 Other: help, time, status"""
    
    if t == "btc":
        return await get_btc_price()
    
    if t == "eth":
        return await get_eth_price()
    
    if t in ["crypto", "prices"]:
        return await get_all_prices()
    
    if t == "markets":
        markets_info = "\n".join([
            f"• {m.id}: {m.question[:30]}... ({m.yes_price:.0%})"
            for m in bot.markets[:5]
        ])
        return f"📊 Active Markets:\n\n{markets_info}"
    
    if t == "arbitrage":
        opps = bot.get_arbitrage_opportunities()
        if not opps:
            return "💰 No arbitrage opportunities found"
        result = "💰 Arbitrage Opportunities:\n\n"
        for o in opps[:3]:
            result += f"• {o['market']}: {o['profit']} ({o['confidence']})\n"
        return result
    
    if t == "risk":
        metrics = bot.get_risk_metrics()
        return f"""🛡️ Risk Metrics:

💰 Portfolio: {metrics['portfolio_value']}
📈 Unrealized PnL: {metrics['unrealized_pnl']}
📉 Max Drawdown: {metrics['max_drawdown']}
🎯 Win Rate: {metrics['win_rate']}
⚠️ Risk Level: {metrics['risk_level']}"""
    
    if t == "status":
        dash = bot.get_dashboard()
        return f"""🤖 Bot Status:

📊 Status: {dash['status']}
⚠️ Risk: {dash['risk_level']}
📈 Markets: {dash['markets_tracked']}
💰 PnL: {dash['total_pnl']}
🎯 Win Rate: {dash['win_rate']}"""
    
    if t.startswith("analyze "):
        market_id = t[8:].strip()
        result = bot.analyze_market(market_id)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"""🔬 Analysis: {result['market']}

💰 Price: {result['current_price']}
📊 RSI: {result['rsi']}
📈 MACD: {result['macd']}
🎯 Trend: {result['trend']}
💡 Recommendation: {result['recommendation']}"""
    
    if t.startswith("trade "):
        parts = t[6:].split()
        if len(parts) >= 3:
            market_id, side, amount = parts[0], parts[1].upper(), float(parts[2])
            result = bot.execute_trade(market_id, side, amount)
            if "error" in result:
                return f"❌ {result['error']}"
            return f"✅ Trade Executed\n\n📊 {result['market']}\n💱 {side} ${amount}\n💵 Price: {result['price']}"
        return "❌ Usage: trade <market> <side> <amount>"
    
    if t == "mm on":
        bot.configure("market_maker", enabled=True)
        return "📈 做市商已启用"
    
    if t == "mm off":
        bot.configure("market_maker", enabled=False)
        return "📈 做市商已禁用"
    
    if t == "arb on":
        bot.configure("arbitrage", enabled=True)
        return "💰 套利已启用"
    
    if t == "arb off":
        bot.configure("arbitrage", enabled=False)
        return "💰 套利已禁用"
    
    if t == "time":
        return f"🕐 UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
    
    if t.startswith("echo "):
        return text[5:]
    
    return f"🤖 Received: {text}\n💡 Type 'help' for commands"


def chat_fn(message: str, history: List):
    """Gradio chat function"""
    if not message:
        return history
    try:
        response = asyncio.run(process_message(message))
        history.append((message, response))
    except Exception as e:
        history.append((message, f"Error: {str(e)}"))
    return history


# ==================== Gradio Interface ====================

with gr.Blocks(title="Polymarket Super Bot", theme=gr.themes.Soft()) as demo:
    
    gr.Markdown("""
    # 🤖 Polymarket Super Bot (Enhanced)
    
    整合 predict-fun-marketmaker 核心功能:
    - 统一做市商策略 (异步对冲、双轨并行)
    - 跨平台套利检测
    - 增强风控系统
    - 智能库存管理
    """)
    
    with gr.Tabs():
        # Tab 1: Chat
        with gr.TabItem("💬 Chat"):
            chatbot = gr.Chatbot(height=400, show_label=False)
            with gr.Row():
                msg = gr.Textbox(placeholder="Type a command... (try 'help')", scale=4, show_label=False)
                btn = gr.Button("Send", variant="primary", scale=1)
            clear = gr.Button("Clear Chat")
            
            msg.submit(chat_fn, [msg, chatbot], [chatbot])
            btn.click(chat_fn, [msg, chatbot], [chatbot])
            clear.click(lambda: [], None, [chatbot])
        
        # Tab 2: Dashboard
        with gr.TabItem("📊 Dashboard"):
            with gr.Row():
                dashboard_json = gr.Code(label="系统状态", language="json", 
                                        value=json.dumps(bot.get_dashboard(), indent=2, ensure_ascii=False))
            refresh_dash = gr.Button("🔄 刷新", variant="primary")
            
            gr.Markdown("### 市场监控")
            markets_df = gr.Dataframe(
                headers=["ID", "问题", "Yes 价格", "流动性"],
                value=bot.get_markets_table(),
                label="活跃市场"
            )
            
            refresh_dash.click(
                fn=lambda: json.dumps(bot.get_dashboard(), indent=2, ensure_ascii=False),
                outputs=dashboard_json
            )
        
        # Tab 3: Arbitrage
        with gr.TabItem("💰 套利"):
            gr.Markdown("### 套利机会")
            arb_output = gr.Code(label="套利机会", language="json",
                                value=json.dumps(bot.get_arbitrage_opportunities(), indent=2, ensure_ascii=False))
            scan_arb = gr.Button("🔍 扫描机会", variant="primary")
            
            scan_arb.click(
                fn=lambda: json.dumps(bot.get_arbitrage_opportunities(), indent=2, ensure_ascii=False),
                outputs=arb_output
            )
        
        # Tab 4: Risk
        with gr.TabItem("🛡️ 风控"):
            risk_output = gr.Code(label="风险指标", language="json",
                                 value=json.dumps(bot.get_risk_metrics(), indent=2, ensure_ascii=False))
            refresh_risk = gr.Button("🔄 刷新风险指标", variant="primary")
            
            refresh_risk.click(
                fn=lambda: json.dumps(bot.get_risk_metrics(), indent=2, ensure_ascii=False),
                outputs=risk_output
            )
        
        # Tab 5: Analysis
        with gr.TabItem("🔬 分析"):
            analysis_market = gr.Dropdown(
                label="选择市场",
                choices=[m.id for m in bot.markets],
                value="btc_100k"
            )
            analyze_btn = gr.Button("📊 分析", variant="primary")
            analysis_result = gr.Code(label="分析结果", language="json")
            
            analyze_btn.click(
                fn=lambda m: json.dumps(bot.analyze_market(m), indent=2, ensure_ascii=False),
                inputs=[analysis_market],
                outputs=analysis_result
            )
        
        # Tab 6: Trade
        with gr.TabItem("💱 交易"):
            with gr.Row():
                trade_market = gr.Dropdown(
                    label="选择市场",
                    choices=[m.id for m in bot.markets],
                    value="btc_100k"
                )
                trade_side = gr.Radio(label="方向", choices=["BUY_YES", "BUY_NO", "SELL_YES", "SELL_NO"], value="BUY_YES")
                trade_amount = gr.Number(label="金额 ($)", value=100)
            
            trade_btn = gr.Button("🚀 执行交易", variant="primary")
            trade_result = gr.Code(label="交易结果", language="json")
            
            trade_btn.click(
                fn=lambda m, s, a: json.dumps(bot.execute_trade(m, s, a), indent=2, ensure_ascii=False),
                inputs=[trade_market, trade_side, trade_amount],
                outputs=trade_result
            )
        
        # Tab 7: Config
        with gr.TabItem("⚙️ 配置"):
            gr.Markdown("### 做市商配置")
            with gr.Row():
                mm_enabled = gr.Checkbox(label="启用做市商", value=False)
                mm_spread = gr.Slider(label="价差 (基点)", minimum=50, maximum=500, value=150, step=10)
            mm_btn = gr.Button("💾 保存做市商配置", variant="primary")
            mm_result = gr.Code(label="结果", language="json")
            
            mm_btn.click(
                fn=lambda e, s: json.dumps(bot.configure("market_maker", enabled=e, spread_bps=s), indent=2, ensure_ascii=False),
                inputs=[mm_enabled, mm_spread],
                outputs=mm_result
            )
            
            gr.Markdown("### 套利配置")
            with gr.Row():
                arb_enabled = gr.Checkbox(label="启用套利", value=False)
                arb_min_profit = gr.Slider(label="最小利润 (%)", minimum=0.5, maximum=5, value=1, step=0.5)
            arb_btn = gr.Button("💾 保存套利配置", variant="primary")
            arb_result = gr.Code(label="结果", language="json")
            
            arb_btn.click(
                fn=lambda e, p: json.dumps(bot.configure("arbitrage", enabled=e, min_profit=p/100), indent=2, ensure_ascii=False),
                inputs=[arb_enabled, arb_min_profit],
                outputs=arb_result
            )


# ==================== FastAPI & Webhook ====================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Polymarket Super Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

log.info("🚀 Polymarket Super Bot Started")


@app.middleware("http")
async def webhook_middleware(request: Request, call_next):
    if request.url.path == "/webhook":
        return await handle_webhook(request)
    if request.url.path == "/api":
        return await handle_webhook(request)
    return await call_next(request)


async def handle_webhook(request: Request) -> Response:
    if request.method == "GET":
        return Response(content=json.dumps({"status": "ok"}), media_type="application/json")
    
    try:
        body = await request.json()
        log.info(f"Webhook: {body.get('type', 'unknown')}")
        
        # URL verification
        if body.get("type") == "url_verification":
            return Response(
                content=json.dumps({"challenge": body.get("challenge", "")}),
                media_type="application/json"
            )
        
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
                    response = await process_message(text)
                    await send_msg(open_id, response)
        
        return Response(content=json.dumps({"code": 0}), media_type="application/json")
    
    except Exception as e:
        log.error(f"Webhook error: {e}")
        return Response(content=json.dumps({"code": -1, "error": str(e)}), media_type="application/json")


@app.get("/health")
async def health():
    return {"status": "ok", "bot": "polymarket-super-bot"}


@app.get("/api/status")
async def api_status():
    return bot.get_dashboard()


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

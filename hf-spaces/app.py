"""
Polymarket Super Bot - Enhanced with Binary Options Pricing

核心功能:
1. Black-Scholes 二元期权定价模型
2. Binance 实时数据源 (Alpha 来源)
3. Maker/Taker 执行策略
4. 波动率建模与预测
5. 飞书 Webhook 集成
"""
import os
import json
import asyncio
import logging
import time
import math
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
API = "https://open.lark.cn/open-apis"

_cache = {"token": None, "expire": 0}


# ==================== Black-Scholes Binary Option Pricing ====================

def norm_cdf(x: float) -> float:
    """标准正态分布累积分布函数"""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_pdf(x: float) -> float:
    """标准正态分布概率密度函数"""
    return math.exp(-0.5 * x ** 2) / math.sqrt(2 * math.pi)


def price_binary_option(
    S: float,  # 当前价格
    K: float,  # 行权价
    T: float,  # 到期时间 (年)
    r: float = 0.05,  # 无风险利率
    sigma: float = 0.5,  # 波动率
    is_call: bool = True
) -> float:
    """
    Black-Scholes 二元期权定价

    二元看涨: C = e^(-rT) * N(d2)
    二元看跌: P = e^(-rT) * N(-d2)

    d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
    d2 = d1 - σ√T
    """
    if T <= 0 or sigma <= 0:
        return 0.5

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    if is_call:
        price = math.exp(-r * T) * norm_cdf(d2)
    else:
        price = math.exp(-r * T) * norm_cdf(-d2)

    return max(0.0, min(1.0, price))


def calculate_implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float = 0.05,
    is_call: bool = True,
    max_iter: int = 100
) -> Optional[float]:
    """计算隐含波动率 (Newton-Raphson 方法)"""
    sigma = 0.5  # 初始猜测

    for _ in range(max_iter):
        theo = price_binary_option(S, K, T, r, sigma, is_call)
        diff = theo - market_price

        if abs(diff) < 1e-6:
            return sigma

        # 计算 Vega
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        vega = -math.exp(-r * T) * norm_pdf(d2) * d1 / sigma if sigma > 0 else 0

        if abs(vega) < 1e-10:
            break

        sigma = sigma - diff / vega
        sigma = max(0.01, min(5.0, sigma))

    return sigma


def calculate_historical_volatility(prices: List[float], annualize: bool = True) -> float:
    """计算历史波动率"""
    if len(prices) < 2:
        return 0.5

    returns = []
    for i in range(1, len(prices)):
        if prices[i] > 0 and prices[i-1] > 0:
            returns.append(math.log(prices[i] / prices[i-1]))

    if not returns:
        return 0.5

    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / len(returns)

    if annualize:
        # 对于 15 分钟 K 线，一年约 35040 个周期
        return math.sqrt(variance * 35040)
    return math.sqrt(variance)


# ==================== Execution Strategies ====================

class StrategyType(Enum):
    MARKET_MAKER = "market_maker"
    TAKER = "taker"
    HYBRID = "hybrid"


@dataclass
class TradeSignal:
    market_id: str
    signal: str  # BUY_YES, BUY_NO, HOLD
    theoretical_price: float
    market_price: float
    edge: float
    volatility: float
    implied_vol: Optional[float]
    strategy: StrategyType
    confidence: float


class ExecutionEngine:
    """执行引擎"""

    def __init__(self, strategy: StrategyType = StrategyType.TAKER):
        self.strategy = strategy
        self.min_edge = 0.02  # 2% 最小边际
        self.maker_spread = 0.015  # 1.5% 价差
        self.taker_slippage = 0.005  # 0.5% 滑点
        self.daily_trades = 0
        self.max_daily_trades = 50
        self.circuit_breaker = False

    def analyze(
        self,
        market_id: str,
        current_price: float,
        strike_price: float,
        time_to_expiry_sec: float,
        market_yes_price: float,
        historical_prices: List[float] = None
    ) -> TradeSignal:
        """分析市场并生成交易信号"""

        # 计算波动率
        vol = calculate_historical_volatility(historical_prices) if historical_prices else 0.5

        # 计算理论价格
        T = time_to_expiry_sec / (365 * 24 * 3600)
        theo = price_binary_option(current_price, strike_price, T, 0.05, vol)

        # 计算边际
        edge = theo - market_yes_price

        # 计算隐含波动率
        iv = calculate_implied_volatility(market_yes_price, current_price, strike_price, T)

        # 生成信号
        if self.strategy == StrategyType.TAKER:
            # Taker 策略: 等待足够大的边际
            min_edge_adjusted = self.min_edge + self.taker_slippage
            if edge > min_edge_adjusted:
                signal = "BUY_YES"
                confidence = min(1.0, edge / 0.1)
            elif edge < -min_edge_adjusted:
                signal = "BUY_NO"
                confidence = min(1.0, abs(edge) / 0.1)
            else:
                signal = "HOLD"
                confidence = 0.5

        elif self.strategy == StrategyType.MARKET_MAKER:
            # Maker 策略: 根据价差挂单
            if abs(edge) > self.min_edge:
                signal = "MAKE_BOTH"
                confidence = min(1.0, abs(edge) / self.maker_spread)
            else:
                signal = "HOLD"
                confidence = 0.5

        else:  # HYBRID
            if abs(edge) > 0.05:
                signal = "BUY_YES" if edge > 0 else "BUY_NO"
                confidence = 0.9
            elif abs(edge) > 0.02:
                signal = "MAKE_BOTH"
                confidence = 0.7
            else:
                signal = "HOLD"
                confidence = 0.5

        return TradeSignal(
            market_id=market_id,
            signal=signal,
            theoretical_price=theo,
            market_price=market_yes_price,
            edge=edge,
            volatility=vol,
            implied_vol=iv,
            strategy=self.strategy,
            confidence=confidence
        )


# ==================== Market Data ====================

@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float
    strike_price: float = 0
    current_price: float = 0
    expiry_minutes: int = 15


class PolymarketBot:
    """Polymarket Super Bot with Binary Options Pricing"""

    def __init__(self):
        self.markets = self._init_markets()
        self.price_history: Dict[str, List[float]] = {}
        self.execution_engine = ExecutionEngine(StrategyType.HYBRID)
        self.stats = {
            "trades": 0,
            "pnl": 0.0,
            "signals": 0
        }

    def _init_markets(self) -> List[Market]:
        """初始化市场"""
        return [
            Market("btc_15m_up", "BTC up in 15 min?", 0.48, 0.52, 150000, 97000, 96500, 15),
            Market("btc_5m_up", "BTC up in 5 min?", 0.50, 0.50, 100000, 97000, 96500, 5),
            Market("eth_15m_up", "ETH up in 15 min?", 0.47, 0.53, 80000, 2700, 2680, 15),
            Market("btc_100k", "BTC reaches $100k?", 0.72, 0.28, 200000, 100000, 96500, 15),
            Market("eth_5k", "ETH exceeds $5,000?", 0.45, 0.55, 120000, 5000, 2700, 15),
        ]

    async def fetch_crypto_prices(self) -> Dict[str, float]:
        """获取加密货币实时价格 (Binance)"""
        prices = {}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # 批量获取价格
                symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
                for symbol in symbols:
                    r = await client.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}")
                    data = r.json()
                    prices[symbol] = float(data.get("price", 0))

                    # 更新历史价格
                    if symbol not in self.price_history:
                        self.price_history[symbol] = []
                    self.price_history[symbol].append(prices[symbol])
                    if len(self.price_history[symbol]) > 100:
                        self.price_history[symbol] = self.price_history[symbol][-100:]

        except Exception as e:
            log.error(f"Error fetching prices: {e}")

        return prices

    def analyze_market(self, market_id: str) -> Dict:
        """分析市场"""
        market = next((m for m in self.markets if m.id == market_id), None)
        if not market:
            return {"error": "Market not found"}

        # 获取历史价格
        symbol = "BTCUSDT" if "btc" in market_id.lower() else "ETHUSDT"
        history = self.price_history.get(symbol, [])

        # 生成信号
        signal = self.execution_engine.analyze(
            market_id=market.id,
            current_price=market.current_price,
            strike_price=market.strike_price,
            time_to_expiry_sec=market.expiry_minutes * 60,
            market_yes_price=market.yes_price,
            historical_prices=history
        )

        self.stats["signals"] += 1

        return {
            "market": market.question,
            "current_price": f"${market.current_price:,.2f}",
            "strike_price": f"${market.strike_price:,.2f}",
            "time_to_expiry": f"{market.expiry_minutes} min",
            "market_yes_price": f"{market.yes_price:.1%}",
            "theoretical_price": f"{signal.theoretical_price:.1%}",
            "edge": f"{signal.edge:.2%}",
            "volatility": f"{signal.volatility:.1%}",
            "implied_volatility": f"{signal.implied_vol:.1%}" if signal.implied_vol else "N/A",
            "signal": signal.signal,
            "confidence": f"{signal.confidence:.0%}",
            "strategy": signal.strategy.value
        }

    def get_dashboard(self) -> Dict:
        """获取仪表盘数据"""
        return {
            "status": "运行中",
            "markets_tracked": len(self.markets),
            "total_signals": self.stats["signals"],
            "trades_executed": self.stats["trades"],
            "daily_pnl": f"${self.stats['pnl']:.2f}",
            "strategy": self.execution_engine.strategy.value,
            "min_edge": f"{self.execution_engine.min_edge:.1%}",
            "circuit_breaker": "正常" if not self.execution_engine.circuit_breaker else "熔断",
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_markets_table(self) -> List[List]:
        """获取市场表格"""
        return [
            [m.id, m.question[:30] + "...", f"{m.yes_price:.1%}", f"${m.liquidity:,}", f"{m.expiry_minutes}m"]
            for m in self.markets
        ]

    def configure_strategy(self, strategy: str, min_edge: float) -> Dict:
        """配置策略"""
        if strategy == "Taker":
            self.execution_engine.strategy = StrategyType.TAKER
        elif strategy == "Market Maker":
            self.execution_engine.strategy = StrategyType.MARKET_MAKER
        else:
            self.execution_engine.strategy = StrategyType.HYBRID

        self.execution_engine.min_edge = min_edge

        return {
            "status": "已更新",
            "strategy": self.execution_engine.strategy.value,
            "min_edge": f"{min_edge:.1%}"
        }


# Create bot instance
bot = PolymarketBot()


# ==================== Lark Integration ====================

async def get_token():
    """获取飞书 token"""
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
    """发送飞书消息"""
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


async def process_message(text: str) -> str:
    """处理消息"""
    t = text.lower().strip()

    if t in ["help", "/help", "?"]:
        return """🤖 Polymarket Binary Options Bot

📊 Commands:
  btc, eth, prices - Crypto prices
  markets - List markets
  analyze <market> - Analyze with BS model
  signal <market> - Get trade signal
  config <strategy> - Set strategy

📈 Pricing: Black-Scholes Model
⚡ Data: Binance Real-time
🎯 Strategies: Maker/Taker/Hybrid"""

    if t == "btc":
        prices = await bot.fetch_crypto_prices()
        btc = prices.get("BTCUSDT", 0)
        return f"🪙 BTC/USDT\n💰 ${btc:,.2f}\n📍 Binance"

    if t == "eth":
        prices = await bot.fetch_crypto_prices()
        eth = prices.get("ETHUSDT", 0)
        return f"💎 ETH/USDT\n💰 ${eth:,.2f}\n📍 Binance"

    if t in ["prices", "crypto"]:
        prices = await bot.fetch_crypto_prices()
        btc = prices.get("BTCUSDT", 0)
        eth = prices.get("ETHUSDT", 0)
        sol = prices.get("SOLUSDT", 0)
        return f"📊 Crypto Prices\n\n🪙 BTC: ${btc:,.2f}\n💎 ETH: ${eth:,.2f}\n🌞 SOL: ${sol:,.2f}"

    if t == "markets":
        markets = "\n".join([f"• {m.id}: {m.question[:25]}... ({m.yes_price:.0%})" for m in bot.markets[:5]])
        return f"📊 Active Markets:\n\n{markets}"

    if t.startswith("analyze "):
        market_id = t[8:].strip()
        result = bot.analyze_market(market_id)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"""🔬 Analysis: {result['market']}

💰 Market Price: {result['market_yes_price']}
📐 Theoretical: {result['theoretical_price']}
📊 Edge: {result['edge']}
📈 Volatility: {result['volatility']}
🎯 Signal: {result['signal']}
💪 Confidence: {result['confidence']}"""

    if t.startswith("signal "):
        market_id = t[7:].strip()
        result = bot.analyze_market(market_id)
        if "error" in result:
            return f"❌ {result['error']}"
        return f"""🎯 Trade Signal

Market: {result['market']}
Signal: {result['signal']}
Edge: {result['edge']}
Confidence: {result['confidence']}"""

    if t == "status":
        dash = bot.get_dashboard()
        return f"""🤖 Bot Status

📊 Markets: {dash['markets_tracked']}
📈 Signals: {dash['total_signals']}
💰 PnL: {dash['daily_pnl']}
🎯 Strategy: {dash['strategy']}"""

    if t == "time":
        return f"🕐 UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"

    return f"🤖 Received: {text}\n💡 Type 'help' for commands"


def chat_fn(message: str, history: List):
    """Gradio chat"""
    if not message:
        return history
    try:
        response = asyncio.run(process_message(message))
        history.append((message, response))
    except Exception as e:
        history.append((message, f"Error: {str(e)}"))
    return history


# ==================== Gradio Interface ====================

with gr.Blocks(title="Polymarket Binary Options Bot", theme=gr.themes.Soft()) as demo:

    gr.Markdown("""
    # 🤖 Polymarket Binary Options Bot

    基于 Black-Scholes 模型的二元期权定价系统

    **核心功能:**
    - 📐 BS 模型计算理论价格
    - 📊 隐含波动率估算
    - ⚡ Binance 实时数据
    - 🎯 Maker/Taker/Hybrid 策略
    """)

    with gr.Tabs():
        # Chat Tab
        with gr.TabItem("💬 Chat"):
            chatbot = gr.Chatbot(height=400)
            with gr.Row():
                msg = gr.Textbox(placeholder="Type 'help' for commands...", scale=4, show_label=False)
                btn = gr.Button("Send", variant="primary", scale=1)
            clear = gr.Button("Clear")

            msg.submit(chat_fn, [msg, chatbot], [chatbot])
            btn.click(chat_fn, [msg, chatbot], [chatbot])
            clear.click(lambda: [], None, [chatbot])

        # Dashboard Tab
        with gr.TabItem("📊 Dashboard"):
            dashboard_json = gr.Code(label="系统状态", language="json",
                                    value=json.dumps(bot.get_dashboard(), indent=2, ensure_ascii=False))
            refresh = gr.Button("🔄 刷新", variant="primary")

            gr.Markdown("### 市场列表")
            markets_df = gr.Dataframe(
                headers=["ID", "问题", "Yes 价格", "流动性", "周期"],
                value=bot.get_markets_table()
            )

            refresh.click(
                fn=lambda: json.dumps(bot.get_dashboard(), indent=2, ensure_ascii=False),
                outputs=dashboard_json
            )

        # Pricing Tab
        with gr.TabItem("📐 BS 定价"):
            gr.Markdown("### Black-Scholes 二元期权定价")

            with gr.Row():
                bs_current = gr.Number(label="当前价格 (S)", value=96500)
                bs_strike = gr.Number(label="行权价 (K)", value=97000)
                bs_time = gr.Number(label="到期时间 (分钟)", value=15)
                bs_vol = gr.Number(label="波动率 (%)", value=50)

            bs_btn = gr.Button("计算理论价格", variant="primary")
            bs_result = gr.Code(label="定价结果", language="json")

            def calculate_bs_price(S, K, T_min, vol_pct):
                T = T_min * 60 / (365 * 24 * 3600)
                sigma = vol_pct / 100
                call_price = price_binary_option(S, K, T, 0.05, sigma, True)
                put_price = price_binary_option(S, K, T, 0.05, sigma, False)
                return json.dumps({
                    "call_price (UP)": f"{call_price:.2%}",
                    "put_price (DOWN)": f"{put_price:.2%}",
                    "sum": f"{call_price + put_price:.2%}",
                    "parameters": {
                        "S": f"${S:,.0f}",
                        "K": f"${K:,.0f}",
                        "T": f"{T_min} min",
                        "sigma": f"{vol_pct:.0%}"
                    }
                }, indent=2, ensure_ascii=False)

            bs_btn.click(
                fn=calculate_bs_price,
                inputs=[bs_current, bs_strike, bs_time, bs_vol],
                outputs=bs_result
            )

        # Analysis Tab
        with gr.TabItem("🔬 分析"):
            analysis_market = gr.Dropdown(
                label="选择市场",
                choices=[m.id for m in bot.markets],
                value="btc_15m_up"
            )
            analyze_btn = gr.Button("📊 分析", variant="primary")
            analysis_result = gr.Code(label="分析结果", language="json")

            analyze_btn.click(
                fn=lambda m: json.dumps(bot.analyze_market(m), indent=2, ensure_ascii=False),
                inputs=[analysis_market],
                outputs=analysis_result
            )

        # Config Tab
        with gr.TabItem("⚙️ 配置"):
            gr.Markdown("### 执行策略配置")

            config_strategy = gr.Radio(
                label="策略类型",
                choices=["Taker", "Market Maker", "Hybrid"],
                value="Hybrid"
            )
            config_edge = gr.Slider(label="最小边际 (%)", minimum=0.5, maximum=5, value=2, step=0.5)

            config_btn = gr.Button("💾 保存配置", variant="primary")
            config_result = gr.Code(label="配置结果", language="json")

            config_btn.click(
                fn=lambda s, e: json.dumps(bot.configure_strategy(s, e/100), indent=2, ensure_ascii=False),
                inputs=[config_strategy, config_edge],
                outputs=config_result
            )


# ==================== FastAPI & Webhook ====================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Polymarket Binary Options Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

log.info("Polymarket Binary Options Bot Started")


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
        log.info(f"Webhook: {body.get('type', 'unknown')}")

        if body.get("type") == "url_verification":
            return Response(
                content=json.dumps({"challenge": body.get("challenge", "")}),
                media_type="application/json"
            )

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
    return {"status": "ok", "bot": "polymarket-binary-options"}


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

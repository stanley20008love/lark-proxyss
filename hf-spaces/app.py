"""AI Agent - Lark Bot with Polymarket Integration"""
import os
import json
import asyncio
import logging
import time
from typing import List
from datetime import datetime, timezone

import gradio as gr
import httpx

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger(__name__)

# Configuration
APP_ID = os.getenv("LARK_APP_ID", "cli_a9f678dd01b8de1b")
APP_SECRET = os.getenv("LARK_APP_SECRET", "4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K")
API = "https://open.lark.cn/open-apis"

# Cache
_cache = {"token": None, "expire": 0}


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
            btc = btc_r.json()
            eth = eth_r.json()
            return f"📊 Crypto Prices\n\n🪙 BTC: ${float(btc['price']):,.2f}\n💎 ETH: ${float(eth['price']):,.2f}\n\n📍 Binance"
    except:
        return "❌ Failed to get prices"


async def process_message(text: str) -> str:
    """Process message and return response"""
    t = text.lower().strip()
    
    if t in ["help", "/help", "?"]:
        return """🤖 AI Agent Commands:

📊 Crypto: btc, eth, crypto
🎯 Polymarket: polymarket, btc15m
💡 Other: help, time"""
    
    if t == "btc":
        return await get_btc_price()
    
    if t == "eth":
        return await get_eth_price()
    
    if t == "crypto":
        return await get_all_prices()
    
    if t == "polymarket":
        return "🎯 Polymarket Prediction Markets\n💡 Use 'btc15m' for BTC 15-minute markets"
    
    if t == "btc15m":
        return "⏱️ BTC 15-Minute Markets\n🎯 Predict BTC direction in 15 minutes\n📍 Polymarket"
    
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


# Gradio Interface
with gr.Blocks(title="AI Agent", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""# 🤖 AI Agent
### Polymarket & Crypto Assistant""")
    
    chatbot = gr.Chatbot(height=400, show_label=False)
    
    with gr.Row():
        msg = gr.Textbox(placeholder="Type a command...", scale=4, show_label=False)
        btn = gr.Button("Send", variant="primary", scale=1)
    
    clear = gr.Button("Clear")
    
    msg.submit(chat_fn, [msg, chatbot], [chatbot])
    btn.click(chat_fn, [msg, chatbot], [chatbot])
    clear.click(lambda: [], None, [chatbot])


# FastAPI & Webhook
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="AI Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

log.info("🚀 AI Agent Started")


@app.middleware("http")
async def webhook_middleware(request: Request, call_next):
    if request.url.path == "/webhook":
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
    return {"status": "ok"}


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

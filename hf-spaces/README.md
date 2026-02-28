---
title: AI Agent - Lark Bot
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
short_description: AI Agent with Polymarket & Crypto integration
---

# 🤖 AI Agent - Lark Bot

AI-powered chatbot for Lark (Feishu) with Polymarket and cryptocurrency integration.

## Features

- 💰 **Crypto Prices**: Real-time BTC and ETH prices from Binance
- 🎯 **Polymarket**: BTC 15-minute prediction market info
- 🔔 **Lark Integration**: Full webhook support
- 🤖 **Gradio Chat**: Interactive web interface

## Commands

| Command | Description |
|---------|-------------|
| `btc` | Get Bitcoin price |
| `eth` | Get Ethereum price |
| `crypto` | Get all crypto prices |
| `polymarket` | Polymarket info |
| `btc15m` | BTC 15-minute markets |
| `help` | Show commands |

## API Endpoints

- `GET /` - Gradio chat interface
- `POST /webhook` - Lark webhook endpoint
- `GET /health` - Health check

## Environment Variables

- `LARK_APP_ID` - Lark application ID
- `LARK_APP_SECRET` - Lark application secret

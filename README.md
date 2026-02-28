# Lark Proxy - AI Agent Webhook

飞书机器人代理服务，集成 Polymarket 预测市场和加密货币价格查询。

## 📁 项目结构

```
├── api/                 # Vercel 部署文件
│   ├── index.js        # Webhook 处理程序
│   ├── package.json
│   └── vercel.json
└── hf-spaces/          # Hugging Face Spaces 部署文件
    ├── app.py          # 主程序
    ├── requirements.txt
    ├── Dockerfile
    └── README.md
```

## 🚀 部署

### 1. Vercel (Webhook 代理)

```bash
cd api
vercel --prod
```

设置环境变量:
- `LARK_APP_ID`
- `LARK_APP_SECRET`
- `HF_SPACE_URL`

### 2. Hugging Face Spaces

将 `hf-spaces/` 目录内容上传到 HF Space (Docker SDK)

## 🎮 命令

| 命令 | 功能 |
|------|------|
| `btc` | BTC 价格 |
| `eth` | ETH 价格 |
| `crypto` | 所有加密货币 |
| `polymarket` | Polymarket 信息 |
| `btc15m` | BTC 15分钟市场 |
| `help` | 帮助 |

## 🔗 链接

- Vercel: `lark-proxyss.vercel.app`
- HF Space: `stanley2000008love-multi-agent-lark-bot.hf.space`

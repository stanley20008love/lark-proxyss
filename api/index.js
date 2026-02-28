// 飞书机器人 - AI 超级智能版 (NVIDIA NIM API)
const LARK_APP_ID = process.env.LARK_APP_ID || 'cli_a9f678dd01b8de1b';
const LARK_APP_SECRET = process.env.LARK_APP_SECRET || '4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K';
const LARK_API = 'https://open.larksuite.com/open-apis';

// NVIDIA NIM API
const NVIDIA_API_KEY = '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';
const NVIDIA_API = 'https://integrate.api.nvidia.com/v1/chat/completions';

// 可用的顶级模型
const AI_MODELS = {
  // 超大模型
  'llama-405b': 'meta/llama-3.1-405b-instruct',
  'deepseek-v3': 'deepseek-ai/deepseek-v3.1',
  'mistral-large': 'mistralai/mistral-large-3-675b-instruct-2512',
  'qwen3': 'qwen/qwen3-235b-a22b',
  
  // 快速响应模型
  'llama-70b': 'meta/llama-3.1-70b-instruct',
  'llama-33-70b': 'meta/llama-3.3-70b-instruct',
  'kimi': 'moonshotai/kimi-k2-instruct',
  
  // 默认模型 (平衡速度和质量)
  'default': 'meta/llama-3.1-70b-instruct'
};

let tokenCache = { token: null, expire: 0 };

// 获取飞书 Token
async function getLarkToken() {
  const now = Date.now() / 1000;
  if (tokenCache.token && now < tokenCache.expire) return tokenCache.token;
  try {
    const res = await fetch(`${LARK_API}/auth/v3/tenant_access_token/internal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: LARK_APP_ID, app_secret: LARK_APP_SECRET })
    });
    const data = await res.json();
    if (data.code === 0) {
      tokenCache = { token: data.tenant_access_token, expire: now + data.expire - 300 };
      return tokenCache.token;
    }
  } catch (e) { console.error('获取token失败:', e); }
  return null;
}

// 发送私聊消息
async function sendLarkMessage(openId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    const res = await fetch(`${LARK_API}/im/v1/messages?receive_id_type=open_id`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ receive_id: openId, msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    const result = await res.json();
    return result.code === 0;
  } catch (e) { return false; }
}

// 回复群消息
async function replyLarkMessage(messageId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    const res = await fetch(`${LARK_API}/im/v1/messages/${messageId}/reply`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    const result = await res.json();
    return result.code === 0;
  } catch (e) { return false; }
}

// 发送到群聊
async function sendToGroup(chatId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    const res = await fetch(`${LARK_API}/im/v1/messages?receive_id_type=chat_id`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ receive_id: chatId, msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    const result = await res.json();
    return result.code === 0;
  } catch (e) { return false; }
}

// ============== NVIDIA NIM AI 对话 ==============

// 调用 NVIDIA NIM API
async function chatWithNVIDIA(message, model = 'default', systemPrompt = null) {
  const modelId = AI_MODELS[model] || AI_MODELS.default;
  
  const system = systemPrompt || `你是AI Agent，一个专业的加密货币和区块链助手。

你的能力:
- 实时加密货币价格查询和分析
- 区块链技术解释
- Polymarket 预测市场分析
- 投资建议和风险管理
- 市场趋势分析

回复风格:
- 简洁专业
- 使用表情符号增加可读性
- 提供有价值的信息
- 对投资问题提醒风险`;

  try {
    const res = await fetch(NVIDIA_API, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NVIDIA_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: modelId,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: message }
        ],
        temperature: 0.7,
        max_tokens: 1024
      })
    });
    
    if (res.ok) {
      const data = await res.json();
      return data.choices?.[0]?.message?.content || null;
    } else {
      console.error('NVIDIA API error:', res.status);
    }
  } catch (e) {
    console.error('AI 对话失败:', e);
  }
  return null;
}

// 使用大模型深度分析
async function deepAnalysis(message) {
  return await chatWithNVIDIA(message, 'llama-70b');
}

// ============== 加密货币数据 ==============

async function getBtcPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    return `🪙 BTC/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    return '❌ 获取 BTC 价格失败，请稍后重试';
  }
}

async function getEthPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    return `💎 ETH/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    return '❌ 获取 ETH 价格失败，请稍后重试';
  }
}

async function getAllCryptoPrices() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,cardano,ripple,chainlink,dogecoin&vs_currencies=usd&include_24hr_change=true', { timeout: 8000 });
    const data = await res.json();
    
    let msg = '📊 加密货币实时行情\n\n';
    
    const coins = [
      { id: 'bitcoin', symbol: '🪙 BTC' },
      { id: 'ethereum', symbol: '💎 ETH' },
      { id: 'solana', symbol: '☀️ SOL' },
      { id: 'chainlink', symbol: '🔗 LINK' },
      { id: 'ripple', symbol: '💧 XRP' },
      { id: 'cardano', symbol: '🔷 ADA' },
      { id: 'dogecoin', symbol: '🐕 DOGE' },
    ];
    
    for (const coin of coins) {
      if (data[coin.id]) {
        const price = data[coin.id].usd?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
        const change = data[coin.id].usd_24h_change;
        const changeStr = change ? (change > 0 ? `📈 +${change.toFixed(2)}%` : `📉 ${change.toFixed(2)}%`) : '';
        msg += `${coin.symbol}: $${price} ${changeStr}\n`;
      }
    }
    
    msg += `\n⏰ ${new Date().toLocaleTimeString()}`;
    return msg;
  } catch (e) {
    return '❌ 无法获取价格数据';
  }
}

async function getMarketOverview() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/global', { timeout: 8000 });
    const data = await res.json();
    
    if (data.data) {
      const btcDom = data.data.market_cap_percentage?.btc?.toFixed(1);
      const ethDom = data.data.market_cap_percentage?.eth?.toFixed(1);
      const totalMcap = (data.data.total_market_cap?.usd / 1e12)?.toFixed(2);
      const change = data.data.market_cap_change_percentage_24h_usd?.toFixed(2);
      
      return `🌍 市场概览

💰 总市值: $${totalMcap}T
📊 24h: ${change > 0 ? '📈' : '📉'} ${change}%

👑 BTC: ${btcDom}%
💎 ETH: ${ethDom}%

⏰ ${new Date().toLocaleTimeString()}`;
    }
  } catch (e) {}
  return '❌ 无法获取市场数据';
}

// ============== 消息处理 ==============

async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  // 帮助
  if (t === 'help' || t === '/help' || t === '?' || t === '帮助' || t === '菜单') {
    return `🤖 AI Agent 超级智能助手

📊 行情查询:
  btc - 比特币价格
  eth - 以太坊价格
  crypto - 主流币行情
  market - 市场概览

🎯 Polymarket:
  polymarket - 预测市场

💡 AI 对话 (任意问题):
  例如: "BTC后市怎么看？"
  "什么是DeFi？"
  "分析一下当前市场"

📝 其他:
  time - 时间
  help - 帮助`;
  }
  
  // 价格查询
  if (t === 'btc' || t === '比特币' || t === 'bitcoin') {
    return await getBtcPrice();
  }
  if (t === 'eth' || t === '以太坊' || t === 'ethereum') {
    return await getEthPrice();
  }
  if (t === 'crypto' || t === '行情' || t === '币价') {
    return await getAllCryptoPrices();
  }
  if (t === 'market' || t === '市场') {
    return await getMarketOverview();
  }
  
  // Polymarket
  if (t === 'polymarket' || t.includes('预测市场')) {
    return `🎯 Polymarket 预测市场

📈 BTC Up or Down 15分钟
预测 BTC 15分钟内涨跌

🔗 polymarket.com

💡 问我关于预测市场的问题
例如: "如何分析预测市场？"`;
  }
  
  // 时间
  if (t === 'time' || t === '时间') {
    const now = new Date();
    return `🕐 ${now.toISOString().replace('T', ' ').substring(0, 19)} UTC`;
  }
  
  // 默认：AI 智能回复
  const aiReply = await chatWithNVIDIA(text);
  if (aiReply) {
    return aiReply;
  }
  
  return `🤖 AI 暂时无法响应

💡 试试这些命令:
  btc - BTC价格
  eth - ETH价格  
  crypto - 所有行情
  help - 帮助`;
}

// ============== 主处理函数 ==============

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  if (req.method === 'GET') {
    return res.status(200).json({ 
      status: 'ok', 
      service: 'lark-ai-super-agent',
      version: '4.0.0',
      ai: 'NVIDIA NIM - Llama 3.1 70B',
      models: Object.keys(AI_MODELS)
    });
  }
  
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (e) {}
  }
  
  // URL验证
  if (body && body.type === 'url_verification') {
    return res.status(200).json({ challenge: String(body.challenge || '') });
  }
  
  // 处理消息
  try {
    if (body && body.header && body.header.event_type === 'im.message.receive_v1') {
      const msg = body.event?.message || {};
      const senderId = body.event?.sender?.sender_id || {};
      
      const chatType = msg.chat_type || 'p2p';
      const messageId = msg.message_id || '';
      const chatId = msg.chat_id || '';
      const openId = senderId.open_id || '';
      
      if (msg.message_type === 'text') {
        let text = '';
        try {
          text = JSON.parse(msg.content || '{}').text || '';
        } catch (e) {
          text = msg.content || '';
        }
        
        // 移除 @机器人
        const mentions = msg.mentions || [];
        for (const mention of mentions) {
          if (mention.key) {
            text = text.replace(mention.key, '').trim();
          }
        }
        
        text = text.trim();
        
        if (text) {
          console.log(`消息: "${text}" (${chatType})`);
          
          const reply = await processMessage(text);
          
          if (chatType === 'group') {
            if (messageId) {
              await replyLarkMessage(messageId, reply);
            } else if (chatId) {
              await sendToGroup(chatId, reply);
            }
          } else {
            if (openId) {
              await sendLarkMessage(openId, reply);
            }
          }
        }
      }
    }
  } catch (e) {
    console.error('处理错误:', e);
  }
  
  return res.status(200).json({ code: 0 });
}

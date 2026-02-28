// 飞书机器人 - AI 超级智能版 (实时搜索 + GLM5)
const LARK_APP_ID = process.env.LARK_APP_ID || 'cli_a9f678dd01b8de1b';
const LARK_APP_SECRET = process.env.LARK_APP_SECRET || '4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K';
const LARK_API = 'https://open.larksuite.com/open-apis';

// NVIDIA NIM API
const NVIDIA_API_KEY = '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';
const NVIDIA_API = 'https://integrate.api.nvidia.com/v1/chat/completions';

// AI 模型
const AI_MODELS = {
  'glm5': 'z-ai/glm5',
  'glm4': 'z-ai/glm4.7',
  'deepseek': 'deepseek-ai/deepseek-v3.1',
  'qwen3': 'qwen/qwen3-235b-a22b',
  'llama-70b': 'meta/llama-3.1-70b-instruct',
  'kimi': 'moonshotai/kimi-k2-instruct',
  'default': 'z-ai/glm5'
};

let tokenCache = { token: null, expire: 0 };

// ============== 飞书 API ==============

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

async function sendLarkMessage(openId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    await fetch(`${LARK_API}/im/v1/messages?receive_id_type=open_id`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ receive_id: openId, msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    return true;
  } catch (e) { return false; }
}

async function replyLarkMessage(messageId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    await fetch(`${LARK_API}/im/v1/messages/${messageId}/reply`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    return true;
  } catch (e) { return false; }
}

async function sendToGroup(chatId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  try {
    await fetch(`${LARK_API}/im/v1/messages?receive_id_type=chat_id`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ receive_id: chatId, msg_type: 'text', content: JSON.stringify({ text: message }) })
    });
    return true;
  } catch (e) { return false; }
}

// ============== 实时搜索功能 ==============

// DuckDuckGo 即时搜索 (免费无需API)
async function searchWeb(query, numResults = 5) {
  try {
    const res = await fetch(`https://api.duckduckgo.com/?q=${encodeURIComponent(query)}&format=json&no_html=1`, {
      timeout: 8000
    });
    const data = await res.json();
    
    let results = [];
    
    // 即时回答
    if (data.AbstractText) {
      results.push({ title: '摘要', snippet: data.AbstractText, url: data.AbstractURL });
    }
    
    // 相关主题
    if (data.RelatedTopics) {
      for (const topic of data.RelatedTopics.slice(0, numResults)) {
        if (topic.Text && topic.FirstURL) {
          results.push({ title: topic.Text.substring(0, 50), snippet: topic.Text, url: topic.FirstURL });
        }
      }
    }
    
    return results.length > 0 ? results : null;
  } catch (e) {
    console.error('DuckDuckGo 搜索失败:', e);
    return null;
  }
}

// 加密货币新闻搜索
async function searchCryptoNews(query = 'bitcoin cryptocurrency news today') {
  try {
    const res = await fetch(`https://api.duckduckgo.com/?q=${encodeURIComponent(query)}&format=json&no_html=1`, {
      timeout: 8000
    });
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('新闻搜索失败:', e);
    return null;
  }
}

// 获取加密货币热搜
async function getCryptoTrending() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/search/trending', { timeout: 8000 });
    const data = await res.json();
    
    if (data.coins) {
      let msg = '🔥 加密货币热搜榜\n\n';
      for (let i = 0; i < Math.min(7, data.coins.length); i++) {
        const coin = data.coins[i].item;
        msg += `${i + 1}. ${coin.name} (${coin.symbol})\n`;
        msg += `   市值排名: #${coin.market_cap_rank || 'N/A'}\n`;
      }
      msg += `\n⏰ ${new Date().toLocaleTimeString()}\n📍 CoinGecko`;
      return msg;
    }
  } catch (e) {
    console.error('热搜获取失败:', e);
  }
  return '❌ 无法获取热搜数据';
}

// 获取恐惧贪婪指数
async function getFearGreedIndex() {
  try {
    const res = await fetch('https://api.alternative.me/fng/', { timeout: 8000 });
    const data = await res.json();
    
    if (data.data && data.data[0]) {
      const fng = data.data[0];
      const value = parseInt(fng.value);
      const classification = fng.value_classification;
      
      let emoji = '😐';
      if (value <= 25) emoji = '😱';
      else if (value <= 45) emoji = '😰';
      else if (value <= 55) emoji = '😐';
      else if (value <= 75) emoji = '😊';
      else emoji = '🤑';
      
      return `${emoji} 恐惧贪婪指数

📊 当前: ${value} (${classification})

📈 极端贪婪: 75-100
😊 贪婪: 55-75
😐 中性: 45-55
😰 恐惧: 25-45
😱 极端恐惧: 0-25

⏰ ${new Date().toLocaleTimeString()}`;
    }
  } catch (e) {
    console.error('恐惧贪婪指数获取失败:', e);
  }
  return '❌ 无法获取恐惧贪婪指数';
}

// ============== NVIDIA AI 对话 ==============

async function chatWithNVIDIA(message, context = null) {
  const system = `你是AI Agent，一个专业的加密货币和区块链智能助手。

核心能力：
📊 实时加密货币价格查询与分析
🔗 区块链技术与DeFi知识解答
🎯 Polymarket预测市场分析
📈 市场趋势与投资策略建议
🔍 实时新闻和热点搜索
⚠️ 风险管理与投资警示

回复风格：
- 专业但易懂
- 使用表情符号增加可读性
- 提供有价值的深度信息
- 投资相关问题必须提醒风险

${context ? `\n当前上下文信息：\n${context}` : ''}`;

  try {
    const res = await fetch(NVIDIA_API, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NVIDIA_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: AI_MODELS.default,
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: message }
        ],
        temperature: 0.7,
        max_tokens: 2000
      })
    });
    
    if (res.ok) {
      const data = await res.json();
      return data.choices?.[0]?.message?.content || null;
    }
  } catch (e) {
    console.error('AI 对话失败:', e);
  }
  return null;
}

// 带搜索增强的 AI 对话
async function chatWithSearch(query) {
  // 先搜索
  const searchResults = await searchWeb(query);
  
  let context = '';
  if (searchResults && searchResults.length > 0) {
    context = '搜索结果：\n';
    for (const r of searchResults.slice(0, 3)) {
      context += `- ${r.snippet}\n`;
    }
  }
  
  // 结合搜索结果回答
  return await chatWithNVIDIA(query, context);
}

// ============== 价格数据 ==============

async function getBtcPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    return `🪙 BTC/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    return '❌ 获取 BTC 价格失败';
  }
}

async function getEthPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    return `💎 ETH/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    return '❌ 获取 ETH 价格失败';
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

// ============== 消息处理 ==============

async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  // 帮助
  if (t === 'help' || t === '/help' || t === '?' || t === '帮助' || t === '菜单') {
    return `🤖 AI Agent 超级智能助手
📍 模型: GLM5 (智谱AI) + 实时搜索

📊 行情查询:
  btc - 比特币价格
  eth - 以太坊价格
  crypto - 主流币行情
  trending - 热搜榜
  fng - 恐惧贪婪指数

🔍 实时搜索:
  news [关键词] - 搜索新闻
  search [关键词] - 网页搜索
  例如: news bitcoin

💡 AI 智能对话:
  直接问任何问题，AI会结合
  实时信息回答你

📝 其他:
  time - 时间
  help - 帮助`;
  }
  
  // 价格
  if (t === 'btc' || t === '比特币') return await getBtcPrice();
  if (t === 'eth' || t === '以太坊') return await getEthPrice();
  if (t === 'crypto' || t === '行情') return await getAllCryptoPrices();
  if (t === 'trending' || t === '热搜') return await getCryptoTrending();
  if (t === 'fng' || t === '恐惧贪婪' || t === '指数') return await getFearGreedIndex();
  
  // 新闻搜索
  if (t.startsWith('news ')) {
    const query = text.substring(5).trim();
    const results = await searchWeb(query + ' cryptocurrency news');
    if (results) {
      let msg = `📰 新闻搜索: ${query}\n\n`;
      for (const r of results.slice(0, 5)) {
        msg += `• ${r.snippet.substring(0, 100)}...\n\n`;
      }
      return msg;
    }
    return '❌ 未找到相关新闻';
  }
  
  // 网页搜索
  if (t.startsWith('search ')) {
    const query = text.substring(7).trim();
    const aiReply = await chatWithSearch(query);
    return aiReply || '❌ 搜索失败';
  }
  
  // 时间
  if (t === 'time' || t === '时间') {
    return `🕐 ${new Date().toISOString().replace('T', ' ').substring(0, 19)} UTC`;
  }
  
  // 默认：AI 智能回复 (带搜索增强)
  const aiReply = await chatWithSearch(text);
  if (aiReply) return aiReply;
  
  return `🤖 AI 暂时无法响应

💡 试试这些命令:
  btc - BTC价格
  crypto - 所有行情
  trending - 热搜榜
  news btc - BTC新闻
  help - 帮助`;
}

// ============== 主处理函数 ==============

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') return res.status(200).end();
  
  if (req.method === 'GET') {
    return res.status(200).json({ 
      status: 'ok', 
      service: 'lark-ai-super-agent',
      version: '6.0.0',
      features: ['GLM5 AI', 'Real-time Search', 'Crypto Data', 'News Aggregation']
    });
  }
  
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (e) {}
  }
  
  if (body && body.type === 'url_verification') {
    return res.status(200).json({ challenge: String(body.challenge || '') });
  }
  
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
        
        const mentions = msg.mentions || [];
        for (const mention of mentions) {
          if (mention.key) text = text.replace(mention.key, '').trim();
        }
        
        text = text.trim();
        
        if (text) {
          console.log(`消息: "${text}" (${chatType})`);
          const reply = await processMessage(text);
          
          if (chatType === 'group') {
            if (messageId) await replyLarkMessage(messageId, reply);
            else if (chatId) await sendToGroup(chatId, reply);
          } else {
            if (openId) await sendLarkMessage(openId, reply);
          }
        }
      }
    }
  } catch (e) {
    console.error('处理错误:', e);
  }
  
  return res.status(200).json({ code: 0 });
}

// 飞书机器人 Webhook - AI 增强版
const HF_SPACE_URL = process.env.HF_SPACE_URL || 'https://stanley2000008love-multi-agent-lark-bot.hf.space';
const LARK_APP_ID = process.env.LARK_APP_ID || 'cli_a9f678dd01b8de1b';
const LARK_APP_SECRET = process.env.LARK_APP_SECRET || '4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K';
const LARK_API = 'https://open.larksuite.com/open-apis';

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

// 回复消息 (群聊使用)
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

// ============== 加密货币数据 ==============

// 多数据源获取 BTC 价格
async function getBtcPrice() {
  const sources = [
    { name: 'Binance', url: 'https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', parse: (d) => d.price },
    { name: 'CoinGecko', url: 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd', parse: (d) => d.bitcoin?.usd },
  ];
  
  for (const source of sources) {
    try {
      const res = await fetch(source.url, { timeout: 5000 });
      const data = await res.json();
      const price = source.parse(data);
      if (price) {
        const formatted = parseFloat(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `🪙 BTC/USDT\n💰 $${formatted}\n📍 ${source.name}\n⏰ ${new Date().toLocaleTimeString()}`;
      }
    } catch (e) {
      console.error(`${source.name} 失败:`, e.message);
    }
  }
  return '❌ 无法获取 BTC 价格，请稍后重试';
}

// 多数据源获取 ETH 价格
async function getEthPrice() {
  const sources = [
    { name: 'Binance', url: 'https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT', parse: (d) => d.price },
    { name: 'CoinGecko', url: 'https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd', parse: (d) => d.ethereum?.usd },
  ];
  
  for (const source of sources) {
    try {
      const res = await fetch(source.url, { timeout: 5000 });
      const data = await res.json();
      const price = source.parse(data);
      if (price) {
        const formatted = parseFloat(price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return `💎 ETH/USDT\n💰 $${formatted}\n📍 ${source.name}\n⏰ ${new Date().toLocaleTimeString()}`;
      }
    } catch (e) {
      console.error(`${source.name} 失败:`, e.message);
    }
  }
  return '❌ 无法获取 ETH 价格，请稍后重试';
}

// 获取所有主流币价格
async function getAllCryptoPrices() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,cardano,ripple&vs_currencies=usd&include_24hr_change=true', { timeout: 8000 });
    const data = await res.json();
    
    let msg = '📊 加密货币实时行情\n\n';
    
    const coins = [
      { id: 'bitcoin', symbol: '🪙 BTC', name: 'Bitcoin' },
      { id: 'ethereum', symbol: '💎 ETH', name: 'Ethereum' },
      { id: 'solana', symbol: '☀️ SOL', name: 'Solana' },
      { id: 'cardano', symbol: '🔷 ADA', name: 'Cardano' },
      { id: 'ripple', symbol: '💧 XRP', name: 'Ripple' },
    ];
    
    for (const coin of coins) {
      if (data[coin.id]) {
        const price = data[coin.id].usd?.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
        const change = data[coin.id].usd_24h_change;
        const changeStr = change ? (change > 0 ? `📈 +${change.toFixed(2)}%` : `📉 ${change.toFixed(2)}%`) : '';
        msg += `${coin.symbol}: $${price} ${changeStr}\n`;
      }
    }
    
    msg += `\n⏰ ${new Date().toLocaleTimeString()}\n📍 CoinGecko`;
    return msg;
  } catch (e) {
    return '❌ 无法获取价格数据，请稍后重试';
  }
}

// ============== Polymarket 数据 ==============

// 获取 Polymarket BTC 15m 市场
async function getPolymarketBT15m() {
  try {
    const res = await fetch('https://clob.polymarket.com/events?active=true&limit=5', { timeout: 10000 });
    const data = await res.json();
    
    if (data && data.length > 0) {
      let msg = '🎯 Polymarket 热门市场\n\n';
      
      for (let i = 0; i < Math.min(3, data.length); i++) {
        const event = data[i];
        const title = event.title || event.question || 'Unknown';
        msg += `${i + 1}. ${title.substring(0, 50)}${title.length > 50 ? '...' : ''}\n`;
      }
      
      msg += '\n🔗 polymarket.com\n💡 输入 "市场详情" 查看更多';
      return msg;
    }
  } catch (e) {
    console.error('Polymarket API 失败:', e);
  }
  
  return `🎯 Polymarket 预测市场

📈 BTC Up or Down 15分钟市场
预测 BTC 在接下来15分钟内上涨还是下跌

🔗 polymarket.com 参与交易
⚠️ 预测市场有风险，请谨慎参与`;
}

// ============== AI 对话功能 ==============

// 调用 AI 进行智能对话
async function chatWithAI(userMessage) {
  try {
    const res = await fetch('https://api.dify.ai/v1/chat-messages', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer app-xxx', // 需要配置 Dify API Key
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        inputs: {},
        query: userMessage,
        user: 'lark-user',
        response_mode: 'blocking'
      })
    });
    
    if (res.ok) {
      const data = await res.json();
      return data.answer || null;
    }
  } catch (e) {
    console.error('AI 对话失败:', e);
  }
  return null;
}

// ============== 市场分析 ==============

// 获取市场概览
async function getMarketOverview() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/global', { timeout: 8000 });
    const data = await res.json();
    
    if (data.data) {
      const btcDominance = data.data.market_cap_percentage?.btc?.toFixed(1);
      const ethDominance = data.data.market_cap_percentage?.eth?.toFixed(1);
      const totalMcap = (data.data.total_market_cap?.usd / 1e12)?.toFixed(2);
      const change24h = data.data.market_cap_change_percentage_24h_usd?.toFixed(2);
      
      return `🌍 市场概览

💰 总市值: $${totalMcap}T
📊 24h 变化: ${change24h > 0 ? '📈' : '📉'} ${change24h}%

👑 BTC 占比: ${btcDominance}%
💎 ETH 占比: ${ethDominance}%

⏰ ${new Date().toLocaleTimeString()}`;
    }
  } catch (e) {
    console.error('市场概览获取失败:', e);
  }
  return '❌ 无法获取市场数据';
}

// ============== 消息处理 ==============

async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  // 帮助
  if (t === 'help' || t === '/help' || t === '?' || t === '帮助' || t === '菜单') {
    return `🤖 AI Agent 智能助手

📊 加密货币行情:
  btc - 比特币价格
  eth - 以太坊价格
  crypto - 主流币行情
  market - 市场概览

🎯 Polymarket:
  polymarket - 热门市场
  btc15m - BTC 15分钟市场

💡 智能对话:
  直接发送任何问题
  我会尝试回答你

📝 其他:
  time - 当前时间
  help - 显示帮助`;
  }
  
  // BTC 价格
  if (t === 'btc' || t === '比特币' || t === 'bitcoin') {
    return await getBtcPrice();
  }
  
  // ETH 价格
  if (t === 'eth' || t === '以太坊' || t === 'ethereum') {
    return await getEthPrice();
  }
  
  // 所有加密货币
  if (t === 'crypto' || t === '行情' || t === '币价' || t === '价格') {
    return await getAllCryptoPrices();
  }
  
  // 市场概览
  if (t === 'market' || t === '市场' || t === '概览') {
    return await getMarketOverview();
  }
  
  // Polymarket
  if (t === 'polymarket' || t.includes('预测') || t === '市场详情') {
    return await getPolymarketBT15m();
  }
  
  // BTC 15m
  if (t === 'btc15m' || t.includes('15分钟') || t.includes('15m')) {
    return `⏱️ BTC 15分钟预测市场

📊 在 Polymarket 上:
预测 BTC 在接下来15分钟内
上涨 ⬆️ 还是下跌 ⬇️

🔗 polymarket.com 参与
⚠️ 高风险预测市场，请谨慎参与

💡 提示: 这是一种短期投机工具
建议结合技术分析使用`;
  }
  
  // 时间
  if (t === 'time' || t === '时间') {
    const now = new Date();
    const utc = now.toISOString().replace('T', ' ').substring(0, 19);
    const beijing = new Date(now.getTime() + 8*3600000).toISOString().replace('T', ' ').substring(0, 19);
    const ny = new Date(now.getTime() - 5*3600000).toISOString().replace('T', ' ').substring(0, 19);
    return `🕐 时区时间

🌍 UTC: ${utc}
🇨🇳 北京: ${beijing}
🇺🇸 纽约: ${ny}`;
  }
  
  // Echo 测试
  if (t.startsWith('echo ')) {
    return text.substring(5);
  }
  
  // 默认：尝试智能回复
  const aiReply = await chatWithAI(text);
  if (aiReply) {
    return aiReply;
  }
  
  // 如果 AI 不可用，返回默认回复
  return `🤖 收到: "${text}"

我理解你想了解 "${text}"

💡 试试以下命令:
  btc - 查看比特币价格
  eth - 查看以太坊价格
  crypto - 查看所有行情
  polymarket - 预测市场
  
或直接问我问题！`;
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
      service: 'lark-ai-agent',
      version: '3.0.0',
      features: ['crypto', 'polymarket', 'ai-chat']
    });
  }
  
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (e) {}
  }
  
  console.log('收到请求:', JSON.stringify(body).substring(0, 500));
  
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
          console.log(`处理消息: "${text}" (${chatType})`);
          
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

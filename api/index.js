// 飞书机器人 Webhook - 完整增强版 (支持群聊)
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
    console.log('私聊发送结果:', result);
    return result.code === 0;
  } catch (e) { console.error('私聊发送失败:', e); return false; }
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
    console.log('群聊回复结果:', result);
    return result.code === 0;
  } catch (e) { console.error('群聊回复失败:', e); return false; }
}

// 发送消息到群聊
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
    console.log('群聊发送结果:', result);
    return result.code === 0;
  } catch (e) { console.error('群聊发送失败:', e); return false; }
}

// 获取 BTC 价格
async function getBtcPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT');
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `🪙 BTC/USDT\n💰 $${price}\n📍 Binance`;
  } catch (e) {
    return '❌ 获取 BTC 价格失败';
  }
}

// 获取 ETH 价格
async function getEthPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT');
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `💎 ETH/USDT\n💰 $${price}\n📍 Binance`;
  } catch (e) {
    return '❌ 获取 ETH 价格失败';
  }
}

// 获取所有加密货币价格
async function getAllCryptoPrices() {
  try {
    const [btcRes, ethRes] = await Promise.all([
      fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT'),
      fetch('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT')
    ]);
    const btc = await btcRes.json();
    const eth = await ethRes.json();
    
    const btcPrice = parseFloat(btc.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    const ethPrice = parseFloat(eth.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    
    return `📊 加密货币实时行情\n\n🪙 BTC: $${btcPrice}\n💎 ETH: $${ethPrice}\n\n📍 数据来源: Binance`;
  } catch (e) {
    return '❌ 获取价格失败';
  }
}

// 转发到 HF Space
async function forwardToHF(body) {
  try {
    const res = await fetch(`${HF_SPACE_URL}/webhook`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return await res.json();
  } catch (e) {
    console.error('HF转发失败:', e);
    return { code: -1, error: e.message };
  }
}

// 处理消息
async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  // 帮助
  if (t === 'help' || t === '/help' || t === '?' || t === '帮助') {
    return `🤖 AI Agent 命令列表

📊 加密货币行情:
  btc - 比特币价格
  eth - 以太坊价格
  crypto - 所有行情

🎯 Polymarket:
  polymarket - 预测市场
  btc15m - BTC 15分钟市场

💡 其他:
  help - 显示帮助
  time - 当前时间
  echo <消息> - 回显消息`;
  }
  
  // BTC 价格
  if (t === 'btc' || t === '比特币') {
    return await getBtcPrice();
  }
  
  // ETH 价格
  if (t === 'eth' || t === '以太坊') {
    return await getEthPrice();
  }
  
  // 所有加密货币
  if (t === 'crypto' || t === '行情') {
    return await getAllCryptoPrices();
  }
  
  // Polymarket
  if (t === 'polymarket' || t.includes('预测')) {
    return `🎯 Polymarket 预测市场

📈 BTC Up or Down 15分钟市场
预测 BTC 在接下来15分钟内上涨还是下跌

💡 输入 btc15m 查看详情`;
  }
  
  // BTC 15m
  if (t === 'btc15m') {
    return `⏱️ BTC 15分钟预测市场

📊 在 Polymarket 上预测:
BTC 在接下来15分钟内会上涨还是下跌？

🔗 访问 polymarket.com 参与
💡 这是高风险预测市场，请谨慎参与`;
  }
  
  // 时间
  if (t === 'time' || t === '时间') {
    const now = new Date();
    const utc = now.toISOString().replace('T', ' ').substring(0, 19);
    const beijing = new Date(now.getTime() + 8*3600000).toISOString().replace('T', ' ').substring(0, 19);
    return `🕐 UTC: ${utc}\n🇨🇳 北京: ${beijing}`;
  }
  
  // Echo
  if (t.startsWith('echo ')) {
    return text.substring(5);
  }
  
  // 默认回复
  return `🤖 收到: ${text}\n\n💡 输入 help 查看可用命令`;
}

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }
  
  // GET 请求 - 健康检查
  if (req.method === 'GET') {
    return res.status(200).json({ 
      status: 'ok', 
      service: 'lark-webhook-proxy',
      version: '2.1.0',
      hf_space: HF_SPACE_URL
    });
  }
  
  // POST 请求处理
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch (e) {}
  }
  
  console.log('收到请求:', JSON.stringify(body).substring(0, 500));
  
  // URL验证 - 必须返回 JSON
  if (body && body.type === 'url_verification') {
    console.log('URL验证 challenge:', body.challenge);
    return res.status(200).json({ challenge: String(body.challenge || '') });
  }
  
  // 处理消息事件
  try {
    if (body && body.header && body.header.event_type === 'im.message.receive_v1') {
      const msg = body.event?.message || {};
      const senderId = body.event?.sender?.sender_id || {};
      
      // 获取消息信息
      const chatType = msg.chat_type || 'p2p';  // p2p = 私聊, group = 群聊
      const messageId = msg.message_id || '';
      const chatId = msg.chat_id || '';
      const openId = senderId.open_id || '';
      
      console.log(`消息类型: ${chatType}, 消息ID: ${messageId}, 群ID: ${chatId}, 用户: ${openId}`);
      
      if (msg.message_type === 'text') {
        let text = '';
        try {
          text = JSON.parse(msg.content || '{}').text || '';
        } catch (e) {
          text = msg.content || '';
        }
        
        // 移除 @机器人 的部分
        const mentions = msg.mentions || [];
        if (mentions.length > 0) {
          // 移除所有 @ 提及
          for (const mention of mentions) {
            if (mention.key) {
              text = text.replace(mention.key, '').trim();
            }
          }
        }
        
        text = text.trim();
        
        if (text) {
          console.log(`处理消息: "${text}" (类型: ${chatType})`);
          
          const reply = await processMessage(text);
          
          if (chatType === 'group') {
            // 群聊：回复到群里
            console.log('群聊回复模式');
            if (messageId) {
              await replyLarkMessage(messageId, reply);
            } else if (chatId) {
              await sendToGroup(chatId, reply);
            }
          } else {
            // 私聊：直接发送
            console.log('私聊回复模式');
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

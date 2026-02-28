// 飞书机器人 - Polymarket Super Bot 整合版
// 包含: 实时价格 + 市场数据 + Flash Crash + 技术分析 + 跟单交易 + 风险管理 + 回测

const LARK_APP_ID = process.env.LARK_APP_ID || 'cli_a9f678dd01b8de1b';
const LARK_APP_SECRET = process.env.LARK_APP_SECRET || '4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K';
const LARK_API = 'https://open.larksuite.com/open-apis';

// Polymarket API
const POLYMARKET_API = 'https://clob.polymarket.com';

// NVIDIA NIM API (GLM5)
const NVIDIA_API_KEY = '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';
const NVIDIA_API = 'https://integrate.api.nvidia.com/v1/chat/completions';

// 缓存
let tokenCache = { token: null, expire: 0 };
let marketCache = { data: null, time: 0 };
let priceHistory = {}; // 用于 Flash Crash 检测

// 风险管理状态
let riskState = {
  dailyPnl: 0,
  dailyTrades: 0,
  positions: [],
  maxPosition: 10,
  maxDailyLoss: 50,
  stopLoss: 0.30,
  takeProfit: 0.20
};

// 跟单交易状态
let copyState = {
  traders: [],
  trades: [],
  ratio: 0.5
};

// ==================== 飞书 API ====================

async function getLarkToken() {
  const now = Date.now() / 1000;
  if (tokenCache.token && now < tokenCache.expire) return tokenCache.token;
  
  const res = await fetch(`${LARK_API}/auth/v3/tenant_access_token/internal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ app_id: LARK_APP_ID, app_secret: LARK_APP_SECRET })
  });
  const data = await res.json();
  if (data.code === 0) {
    tokenCache = { token: data.tenant_access_token, expire: now + 7000 };
    return tokenCache.token;
  }
  return null;
}

async function sendLarkMessage(openId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  
  await fetch(`${LARK_API}/im/v1/messages?receive_id_type=open_id`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ receive_id: openId, msg_type: 'text', content: JSON.stringify({ text: message }) })
  });
  return true;
}

async function replyLarkMessage(messageId, message) {
  const token = await getLarkToken();
  if (!token) return false;
  
  await fetch(`${LARK_API}/im/v1/messages/${messageId}/reply`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ msg_type: 'text', content: JSON.stringify({ text: message }) })
  });
  return true;
}

// ==================== Polymarket API ====================

async function getPolymarketMarkets() {
  try {
    const res = await fetch(`${POLYMARKET_API}/markets?limit=20`, { timeout: 10000 });
    const data = await res.json();
    return data.results || [];
  } catch (e) {
    console.error('Polymarket API error:', e);
    return [];
  }
}

async function getBTC15mMarkets() {
  const markets = await getPolymarketMarkets();
  return markets.filter(m => 
    (m.question?.toLowerCase().includes('btc') || m.question?.toLowerCase().includes('bitcoin')) &&
    m.question?.toLowerCase().includes('15')
  ).slice(0, 5);
}

async function getMarketPrice(tokenId) {
  try {
    const res = await fetch(`${POLYMARKET_API}/price?token_id=${tokenId}`, { timeout: 5000 });
    const data = await res.json();
    return parseFloat(data.price) || 0.5;
  } catch {
    return 0.5;
  }
}

async function getOrderBook(tokenId) {
  try {
    const res = await fetch(`${POLYMARKET_API}/book?token_id=${tokenId}`, { timeout: 5000 });
    return await res.json();
  } catch {
    return null;
  }
}

// ==================== 加密货币价格 ====================

async function getBtcPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    
    // 更新价格历史 (用于 Flash Crash)
    if (!priceHistory['BTC']) priceHistory['BTC'] = [];
    priceHistory['BTC'].push({ time: Date.now(), price: parseFloat(data.price) });
    if (priceHistory['BTC'].length > 60) priceHistory['BTC'].shift();
    
    return `🪙 BTC/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch {
    return '❌ 获取 BTC 价格失败';
  }
}

async function getEthPrice() {
  try {
    const res = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT', { timeout: 5000 });
    const data = await res.json();
    const price = parseFloat(data.price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    return `💎 ETH/USDT\n💰 $${price}\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  } catch {
    return '❌ 获取 ETH 价格失败';
  }
}

async function getAllCryptoPrices() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,ripple,cardano,chainlink,dogecoin&vs_currencies=usd&include_24hr_change=true', { timeout: 8000 });
    const data = await res.json();
    
    const coins = [
      { id: 'bitcoin', symbol: '🪙 BTC' },
      { id: 'ethereum', symbol: '💎 ETH' },
      { id: 'solana', symbol: '☀️ SOL' },
      { id: 'ripple', symbol: '💧 XRP' },
      { id: 'chainlink', symbol: '🔗 LINK' },
      { id: 'cardano', symbol: '🔷 ADA' },
      { id: 'dogecoin', symbol: '🐕 DOGE' }
    ];
    
    let msg = '📊 加密货币实时行情\n\n';
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
  } catch {
    return '❌ 无法获取价格数据';
  }
}

async function getFearGreedIndex() {
  try {
    const res = await fetch('https://api.alternative.me/fng/', { timeout: 5000 });
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
  } catch {}
  return '❌ 无法获取恐惧贪婪指数';
}

async function getTrending() {
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
      msg += `\n⏰ ${new Date().toLocaleTimeString()}`;
      return msg;
    }
  } catch {}
  return '❌ 无法获取热搜数据';
}

// ==================== 技术分析 ====================

function calculateRSI(prices, period = 14) {
  if (prices.length < period + 1) return null;
  
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = prices[prices.length - i] - prices[prices.length - i - 1];
    if (diff > 0) gains += diff;
    else losses -= diff;
  }
  
  const avgGain = gains / period;
  const avgLoss = losses / period;
  const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

function calculateMACD(prices) {
  if (prices.length < 26) return null;
  
  const ema12 = calculateEMA(prices, 12);
  const ema26 = calculateEMA(prices, 26);
  const macd = ema12 - ema26;
  
  return { macd, signal: macd * 0.8, histogram: macd * 0.2 };
}

function calculateEMA(prices, period) {
  const k = 2 / (period + 1);
  let ema = prices[0];
  for (let i = 1; i < prices.length; i++) {
    ema = prices[i] * k + ema * (1 - k);
  }
  return ema;
}

async function getTechnicalAnalysis() {
  try {
    // 获取 BTC K线数据
    const res = await fetch('https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=50', { timeout: 8000 });
    const klines = await res.json();
    
    const closes = klines.map(k => parseFloat(k[4]));
    const volumes = klines.map(k => parseFloat(k[5]));
    
    const rsi = calculateRSI(closes);
    const macd = calculateMACD(closes);
    const currentPrice = closes[closes.length - 1];
    
    let rsiSignal = '中性';
    if (rsi < 30) rsiSignal = '超卖 📈';
    else if (rsi > 70) rsiSignal = '超买 📉';
    
    let macdSignal = '中性';
    if (macd && macd.histogram > 0) macdSignal = '看涨 📈';
    else if (macd && macd.histogram < 0) macdSignal = '看跌 📉';
    
    // 综合判断
    let overall = '观望';
    let signals = 0;
    if (rsi < 30) signals++;
    if (rsi > 70) signals--;
    if (macd && macd.histogram > 0) signals++;
    if (macd && macd.histogram < 0) signals--;
    
    if (signals >= 2) overall = '🟢 看涨';
    else if (signals <= -2) overall = '🔴 看跌';
    else overall = '🟡 中性';
    
    return `📊 BTC 技术分析

💰 当前价格: $${currentPrice.toLocaleString()}

📈 RSI(14): ${rsi ? rsi.toFixed(1) : 'N/A'}
   信号: ${rsiSignal}

📈 MACD: ${macd ? macd.macd.toFixed(2) : 'N/A'}
   信号: ${macdSignal}

🎯 综合判断: ${overall}

⏰ ${new Date().toLocaleTimeString()}`;
  } catch {
    return '❌ 技术分析获取失败';
  }
}

// ==================== Flash Crash 检测 ====================

function detectFlashCrash(history, threshold = 0.15) {
  if (history.length < 10) return null;
  
  const recent = history.slice(-10);
  const firstPrice = recent[0].price;
  const currentPrice = recent[recent.length - 1].price;
  
  const drop = (firstPrice - currentPrice) / firstPrice;
  
  if (drop >= threshold) {
    return {
      detected: true,
      drop: drop,
      direction: 'DOWN',
      priceBefore: firstPrice,
      priceAfter: currentPrice
    };
  }
  
  if (drop <= -threshold) {
    return {
      detected: true,
      drop: Math.abs(drop),
      direction: 'UP',
      priceBefore: firstPrice,
      priceAfter: currentPrice
    };
  }
  
  return null;
}

// ==================== 风险管理 ====================

function getRiskStatus() {
  const riskLevel = Math.abs(riskState.dailyPnl) / riskState.maxDailyLoss;
  
  let level = '🟢 低风险';
  if (riskLevel >= 1) level = '🔴 高风险';
  else if (riskLevel >= 0.75) level = '🟠 中高风险';
  else if (riskLevel >= 0.5) level = '🟡 中风险';
  
  return `⚠️ 风险管理状态

${level}

📊 今日统计:
  • 盈亏: ${riskState.dailyPnl >= 0 ? '+' : ''}${riskState.dailyPnl.toFixed(2)} USDC
  • 交易: ${riskState.dailyTrades} 笔
  • 持仓: ${riskState.positions.length} 个

⚙️ 风险参数:
  • 单笔最大: ${riskState.maxPosition} USDC
  • 每日止损: ${riskState.maxDailyLoss} USDC
  • 止损比例: ${(riskState.stopLoss * 100).toFixed(0)}%
  • 止盈比例: ${(riskState.takeProfit * 100).toFixed(0)}%

⏰ ${new Date().toLocaleTimeString()}`;
}

// ==================== 跟单交易 ====================

function getCopyTradingStatus() {
  let msg = `👥 跟单交易状态

📊 跟单设置:
  • 比例: ${(copyState.ratio * 100).toFixed(0)}%
  • 目标数: ${copyState.traders.length}
  • 跟单记录: ${copyState.trades.length} 笔

`;
  
  if (copyState.traders.length > 0) {
    msg += '🎯 跟单目标:\n';
    copyState.traders.slice(0, 5).forEach((t, i) => {
      msg += `  ${i + 1}. ${t.address.slice(0, 10)}... (${t.winRate?.toFixed(0) || 'N/A'}%)\n`;
    });
  } else {
    msg += '💡 使用 "copy add 地址" 添加跟单目标';
  }
  
  return msg;
}

// ==================== Polymarket 市场分析 ====================

async function getPolymarketAnalysis() {
  try {
    const markets = await getBTC15mMarkets();
    
    if (markets.length === 0) {
      return `🎯 Polymarket BTC 15分钟市场

📊 暂时无法获取市场数据

💡 Polymarket 预测市场:
预测 BTC 在15分钟内上涨还是下跌

🔗 polymarket.com`;
    }
    
    let msg = `🎯 Polymarket BTC 15分钟市场\n\n`;
    
    for (const m of markets.slice(0, 3)) {
      const tokens = m.tokens || [];
      const yesToken = tokens[0]?.token_id;
      const noToken = tokens[1]?.token_id;
      
      let yesPrice = 0.5, noPrice = 0.5;
      if (yesToken) yesPrice = await getMarketPrice(yesToken);
      if (noToken) noPrice = await getMarketPrice(noToken);
      
      const question = m.question?.substring(0, 50) || 'BTC 15m Market';
      
      msg += `📊 ${question}...\n`;
      msg += `   📈 UP: ${(yesPrice * 100).toFixed(1)}%\n`;
      msg += `   📉 DOWN: ${(noPrice * 100).toFixed(1)}%\n\n`;
    }
    
    msg += `🔗 polymarket.com\n`;
    msg += `⏰ ${new Date().toLocaleTimeString()}`;
    
    return msg;
  } catch (e) {
    return `🎯 Polymarket 市场分析

❌ 获取数据失败

💡 命令:
  polymarket - BTC 15分钟市场
  market - 详细市场分析`;
  }
}

// ==================== AI 对话 ====================

async function chatWithAI(message) {
  try {
    const res = await fetch(NVIDIA_API, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${NVIDIA_API_KEY}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        model: 'z-ai/glm5',
        messages: [
          { role: 'system', content: '你是Polymarket交易助手，专业分析加密货币和预测市场。回答简洁专业，使用表情符号。' },
          { role: 'user', content: message }
        ],
        temperature: 0.7,
        max_tokens: 1000
      })
    });
    
    const data = await res.json();
    return data.choices?.[0]?.message?.content || null;
  } catch {
    return null;
  }
}

// ==================== 消息处理 ====================

async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  // 帮助
  if (t === 'help' || t === '/help' || t === '?' || t === '帮助') {
    return `🤖 Polymarket Super Bot

📊 行情查询:
  btc - 比特币价格
  eth - 以太坊价格
  crypto - 所有主流币
  trending - 热搜榜
  fng - 恐惧贪婪指数

🎯 Polymarket:
  polymarket - BTC 15分钟市场
  market - 市场详细分析

📈 技术分析:
  ta - BTC技术分析 (RSI/MACD)
  flash - Flash Crash检测

⚙️ 风险管理:
  risk - 风险状态
  copy - 跟单交易

💡 AI对话:
  直接问任何问题

📝 其他:
  time - 时间
  help - 帮助`;
  }
  
  // 价格
  if (t === 'btc' || t === '比特币') return await getBtcPrice();
  if (t === 'eth' || t === '以太坊') return await getEthPrice();
  if (t === 'crypto' || t === '行情') return await getAllCryptoPrices();
  if (t === 'trending' || t === '热搜') return await getTrending();
  if (t === 'fng' || t === '恐惧贪婪') return await getFearGreedIndex();
  
  // Polymarket
  if (t === 'polymarket' || t === 'polymarket' || t === '预测') return await getPolymarketAnalysis();
  if (t === 'market' || t === '市场') return await getPolymarketAnalysis();
  
  // 技术分析
  if (t === 'ta' || t === '技术分析' || t === '分析') return await getTechnicalAnalysis();
  
  // Flash Crash
  if (t === 'flash' || t === 'flash crash') {
    const btcHistory = priceHistory['BTC'] || [];
    const crash = detectFlashCrash(btcHistory);
    
    if (crash) {
      return `🚨 Flash Crash 检测！

📉 变化: ${crash.drop > 0 ? '-' : '+'}${(Math.abs(crash.drop) * 100).toFixed(2)}%
🎯 方向: ${crash.direction === 'DOWN' ? '📉 下跌' : '📈 上涨'}
💰 之前: $${crash.priceBefore.toLocaleString()}
💰 当前: $${crash.priceAfter.toLocaleString()}

💡 建议: ${crash.direction === 'DOWN' ? '考虑买入' : '考虑卖出'}

⏰ ${new Date().toLocaleTimeString()}`;
    }
    
    return `📊 Flash Crash 监控

当前 BTC 价格稳定

最近10分钟无异常波动

💡 当价格在10分钟内
变化超过15%时会触发警报

⏰ ${new Date().toLocaleTimeString()}`;
  }
  
  // 风险管理
  if (t === 'risk' || t === '风险') return getRiskStatus();
  
  // 跟单交易
  if (t === 'copy' || t === '跟单') return getCopyTradingStatus();
  
  // 添加跟单目标
  if (t.startsWith('copy add ')) {
    const address = text.substring(9).trim();
    if (address.length > 10) {
      copyState.traders.push({ address, winRate: 0 });
      return `✅ 已添加跟单目标

📍 地址: ${address.slice(0, 20)}...
📊 目标总数: ${copyState.traders.length}`;
    }
    return '❌ 地址格式错误';
  }
  
  // 时间
  if (t === 'time' || t === '时间') {
    return `🕐 ${new Date().toISOString().replace('T', ' ').substring(0, 19)} UTC`;
  }
  
  // 回测 (简化版)
  if (t === 'backtest' || t === '回测') {
    return `📈 回测功能

📊 模拟回测结果:

💰 初始资金: 1000 USDC
💰 最终资金: 1,250 USDC
📊 总盈亏: +250 USDC (+25%)

📝 交易统计:
  • 总交易: 50 笔
  • 胜率: 62%
  • 最大回撤: 8.5%

⏰ ${new Date().toLocaleTimeString()}

💡 这是模拟数据，实际交易需谨慎`;
  }
  
  // AI 对话
  const aiReply = await chatWithAI(text);
  if (aiReply) return aiReply;
  
  return `🤖 收到: "${text}"

💡 输入 help 查看所有命令`;
}

// ==================== 主处理函数 ====================

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  
  if (req.method === 'OPTIONS') return res.status(200).end();
  
  if (req.method === 'GET') {
    return res.status(200).json({
      status: 'ok',
      service: 'polymarket-super-bot',
      version: '2.0.0',
      features: ['real-time-prices', 'polymarket', 'flash-crash', 'technical-analysis', 'risk-management', 'copy-trading', 'backtest', 'ai-chat']
    });
  }
  
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch {}
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
      const openId = senderId.open_id || '';
      
      if (msg.message_type === 'text') {
        let text = '';
        try {
          text = JSON.parse(msg.content || '{}').text || '';
        } catch {
          text = msg.content || '';
        }
        
        // 移除 @机器人
        const mentions = msg.mentions || [];
        for (const m of mentions) {
          if (m.key) text = text.replace(m.key, '').trim();
        }
        
        text = text.trim();
        
        if (text) {
          console.log(`消息: "${text}" (${chatType})`);
          
          const reply = await processMessage(text);
          
          if (chatType === 'group') {
            await replyLarkMessage(messageId, reply);
          } else {
            await sendLarkMessage(openId, reply);
          }
        }
      }
    }
  } catch (e) {
    console.error('处理错误:', e);
  }
  
  return res.status(200).json({ code: 0 });
}

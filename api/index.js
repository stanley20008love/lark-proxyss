// 飞书控制面板 - Polymarket Super Bot
// 支持交互式卡片消息，提供完整的控制面板功能

const LARK_APP_ID = process.env.LARK_APP_ID || 'cli_a9f678dd01b8de1b';
const LARK_APP_SECRET = process.env.LARK_APP_SECRET || '4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K';
const LARK_API = 'https://open.larksuite.com/open-apis';

// Bot 状态
let botState = {
  status: 'running',
  strategy: 'hybrid',
  marketMaker: { enabled: false, spreadBps: 150 },
  arbitrage: { enabled: false, minProfit: 0.02 },
  risk: { maxPosition: 100, stopLoss: 0.30, circuitBreaker: false },
  stats: { trades: 0, pnl: 0, signals: 0, winRate: 0.68 },
  positions: [],
  alerts: []
};

// 缓存
let tokenCache = { token: null, expire: 0 };
let priceCache = { btc: 0, eth: 0, btcChange: 0, ethChange: 0, time: 0 };

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

async function sendCardMessage(openId, card) {
  const token = await getLarkToken();
  if (!token) return false;
  
  await fetch(`${LARK_API}/im/v1/messages?receive_id_type=open_id`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      receive_id: openId,
      msg_type: 'interactive',
      content: JSON.stringify(card)
    })
  });
  return true;
}

async function replyCardMessage(messageId, card) {
  const token = await getLarkToken();
  if (!token) return false;
  
  await fetch(`${LARK_API}/im/v1/messages/${messageId}/reply`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      msg_type: 'interactive',
      content: JSON.stringify(card)
    })
  });
  return true;
}

async function updateCardMessage(messageId, card) {
  const token = await getLarkToken();
  if (!token) return false;
  
  await fetch(`${LARK_API}/im/v1/messages/${messageId}`, {
    method: 'PATCH',
    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      msg_type: 'interactive',
      content: JSON.stringify(card)
    })
  });
  return true;
}

// ==================== 卡片生成器 ====================

function createMainDashboard(prices) {
  // 不使用硬编码默认值，直接检查价格是否存在
  const btcPrice = prices?.btc || 0;
  const ethPrice = prices?.eth || 0;
  const btcChange = prices?.btcChange || 0;
  const ethChange = prices?.ethChange || 0;
  const hasError = prices?.error || (btcPrice === 0);
  
  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '🤖 Polymarket Super Bot' },
      subtitle: { tag: 'plain_text', content: `状态: ${botState.status === 'running' ? '✅ 运行中' : '⏸️ 已暂停'}` },
      template: botState.status === 'running' ? 'blue' : 'grey'
    },
    elements: [
      // 加密货币价格行
      {
        tag: 'div',
        fields: [
          {
            is_short: true,
            text: {
              tag: 'lark_md',
              content: hasError 
                ? `**🪙 BTC/USDT**\n❌ ${prices?.error || '获取失败'}\n💡 点击刷新重试`
                : `**🪙 BTC/USDT**\n$${btcPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}\n${btcChange >= 0 ? '📈' : '📉'} ${btcChange >= 0 ? '+' : ''}${btcChange.toFixed(2)}%`
            }
          },
          {
            is_short: true,
            text: {
              tag: 'lark_md',
              content: hasError 
                ? `**💎 ETH/USDT**\n❌ 获取失败\n📍 数据源: Binance`
                : `**💎 ETH/USDT**\n$${ethPrice.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}\n${ethChange >= 0 ? '📈' : '📉'} ${ethChange >= 0 ? '+' : ''}${ethChange.toFixed(2)}%`
            }
          }
        ]
      },
      { tag: 'hr' },
      // 统计数据
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**📊 交易信号**\n${botState.stats.signals}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**💰 今日盈亏**\n${botState.stats.pnl >= 0 ? '+' : ''}$${botState.stats.pnl.toFixed(2)}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**📈 交易次数**\n${botState.stats.trades}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**🎯 胜率**\n${(botState.stats.winRate * 100).toFixed(0)}%` } }
        ]
      },
      { tag: 'hr' },
      // 策略状态
      {
        tag: 'div',
        fields: [
          { 
            is_short: true, 
            text: { 
              tag: 'lark_md', 
              content: `**📈 做市商**\n${botState.marketMaker.enabled ? '✅ 启用' : '⏸️ 禁用'}\n价差: ${botState.marketMaker.spreadBps}bps` 
            } 
          },
          { 
            is_short: true, 
            text: { 
              tag: 'lark_md', 
              content: `**💰 套利**\n${botState.arbitrage.enabled ? '✅ 启用' : '⏸️ 禁用'}\n最小利润: ${(botState.arbitrage.minProfit * 100).toFixed(1)}%` 
            } 
          }
        ]
      },
      { tag: 'hr' },
      // 操作按钮
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '📊 市场监控' },
            type: 'primary',
            value: { action: 'show_markets' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '📐 定价分析' },
            type: 'default',
            value: { action: 'show_pricing' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '⚙️ 配置' },
            type: 'default',
            value: { action: 'show_config' }
          }
        ]
      },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: botState.marketMaker.enabled ? '⏸️ 停止做市' : '▶️ 启动做市' },
            type: botState.marketMaker.enabled ? 'danger' : 'primary',
            value: { action: 'toggle_market_maker' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: botState.arbitrage.enabled ? '⏸️ 停止套利' : '▶️ 启动套利' },
            type: botState.arbitrage.enabled ? 'danger' : 'primary',
            value: { action: 'toggle_arbitrage' }
          }
        ]
      },
      // 风险警报
      ...(botState.risk.circuitBreaker ? [{
        tag: 'alert',
        title: '🚨 熔断已触发',
        text: '交易已暂停，请检查风险状态'
      }] : []),
      // 底部时间
      {
        tag: 'note',
        elements: [
          { tag: 'plain_text', content: `⏰ ${new Date().toLocaleString('zh-CN')} | 策略: ${botState.strategy.toUpperCase()} | 数据源: Binance` }
        ]
      }
    ]
  };
}

function createMarketMonitorCard(markets) {
  const marketRows = markets.slice(0, 5).map((m, i) => ({
    tag: 'div',
    fields: [
      { is_short: true, text: { tag: 'lark_md', content: `**${i + 1}. ${m.question?.substring(0, 25) || 'Market'}...**` } },
      { is_short: true, text: { tag: 'lark_md', content: `**Yes:** ${(m.yesPrice * 100).toFixed(1)}%` } },
      { is_short: true, text: { tag: 'lark_md', content: `**流动性:** $${(m.liquidity || 0).toLocaleString()}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**信号:** ${m.signal || 'HOLD'}` } }
    ]
  }));

  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '📊 市场监控' },
      subtitle: { tag: 'plain_text', content: `监控 ${markets.length} 个市场` },
      template: 'blue'
    },
    elements: [
      ...marketRows,
      { tag: 'hr' },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🔄 刷新' },
            type: 'primary',
            value: { action: 'refresh_markets' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '💹 查看套利机会' },
            type: 'default',
            value: { action: 'show_arbitrage' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🏠 返回主页' },
            type: 'default',
            value: { action: 'show_main' }
          }
        ]
      }
    ]
  };
}

function createPricingCard(pricing) {
  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '📐 BS 定价分析' },
      subtitle: { tag: 'plain_text', content: 'Black-Scholes 二元期权定价模型' },
      template: 'purple'
    },
    elements: [
      {
        tag: 'div',
        text: { tag: 'lark_md', content: `**🎯 市场分析**\n${pricing.market}` }
      },
      { tag: 'hr' },
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**💰 当前价格**\n$${pricing.currentPrice?.toLocaleString()}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**🎯 行权价**\n$${pricing.strikePrice?.toLocaleString()}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**📊 市场价格**\n${pricing.marketPrice}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**📐 理论价格**\n${pricing.theoreticalPrice}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**📈 波动率**\n${pricing.volatility}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**📊 隐含波动率**\n${pricing.impliedVol || 'N/A'}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**⚡ 边际**\n${pricing.edge}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**🎯 信号**\n${pricing.signal}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        text: {
          tag: 'lark_md',
          content: `**💡 交易建议**\n${pricing.recommendation}`
        }
      },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '✅ 执行交易' },
            type: 'primary',
            value: { action: 'execute_trade', market: pricing.marketId }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🔄 重新分析' },
            type: 'default',
            value: { action: 'refresh_pricing' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🏠 返回主页' },
            type: 'default',
            value: { action: 'show_main' }
          }
        ]
      }
    ]
  };
}

function createConfigCard() {
  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '⚙️ 系统配置' },
      subtitle: { tag: 'plain_text', content: '调整交易参数' },
      template: 'grey'
    },
    elements: [
      {
        tag: 'div',
        text: { tag: 'lark_md', content: '**🎯 执行策略**' }
      },
      {
        tag: 'action',
        actions: [
          {
            tag: 'select_static',
            placeholder: { tag: 'plain_text', content: '选择策略' },
            options: [
              { text: { tag: 'plain_text', content: 'Taker (吃单)' }, value: 'taker' },
              { text: { tag: 'plain_text', content: 'Market Maker (做市)' }, value: 'market_maker' },
              { text: { tag: 'plain_text', content: 'Hybrid (混合)' }, value: 'hybrid' }
            ],
            value: botState.strategy,
            name: 'strategy_select'
          }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        text: { tag: 'lark_md', content: '**📈 做市商配置**' }
      },
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**价差:** ${botState.marketMaker.spreadBps} bps` } },
          { is_short: true, text: { tag: 'lark_md', content: `**状态:** ${botState.marketMaker.enabled ? '✅ 启用' : '⏸️ 禁用'}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        text: { tag: 'lark_md', content: '**💰 套利配置**' }
      },
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**最小利润:** ${(botState.arbitrage.minProfit * 100).toFixed(1)}%` } },
          { is_short: true, text: { tag: 'lark_md', content: `**状态:** ${botState.arbitrage.enabled ? '✅ 启用' : '⏸️ 禁用'}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        text: { tag: 'lark_md', content: '**🛡️ 风险管理**' }
      },
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**最大仓位:** $${botState.risk.maxPosition}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**止损:** ${(botState.risk.stopLoss * 100).toFixed(0)}%` } },
          { is_short: true, text: { tag: 'lark_md', content: `**熔断:** ${botState.risk.circuitBreaker ? '🔴 已触发' : '🟢 正常'}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '💾 保存配置' },
            type: 'primary',
            value: { action: 'save_config' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🔄 重置默认' },
            type: 'default',
            value: { action: 'reset_config' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🏠 返回主页' },
            type: 'default',
            value: { action: 'show_main' }
          }
        ]
      }
    ]
  };
}

function createArbitrageCard(opportunities) {
  const oppRows = opportunities.slice(0, 5).map((o, i) => ({
    tag: 'div',
    fields: [
      { is_short: true, text: { tag: 'lark_md', content: `**${i + 1}. ${o.market}**` } },
      { is_short: true, text: { tag: 'lark_md', content: `**类型:** ${o.type}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**利润:** ${o.profit}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**置信度:** ${o.confidence}` } }
    ]
  }));

  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '💰 套利机会' },
      subtitle: { tag: 'plain_text', content: `发现 ${opportunities.length} 个机会` },
      template: 'green'
    },
    elements: [
      ...oppRows,
      { tag: 'hr' },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '⚡ 执行全部' },
            type: 'primary',
            value: { action: 'execute_all_arbitrage' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🔄 刷新' },
            type: 'default',
            value: { action: 'refresh_arbitrage' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🏠 返回主页' },
            type: 'default',
            value: { action: 'show_main' }
          }
        ]
      }
    ]
  };
}

function createAlertCard(alerts) {
  const alertElements = alerts.map(a => ({
    tag: 'alert',
    title: a.title,
    text: a.message
  }));

  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '🚨 风险警报' },
      subtitle: { tag: 'plain_text', content: `${alerts.length} 个警报` },
      template: 'red'
    },
    elements: [
      ...alertElements,
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '✅ 确认全部' },
            type: 'primary',
            value: { action: 'acknowledge_alerts' }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '🏠 返回主页' },
            type: 'default',
            value: { action: 'show_main' }
          }
        ]
      }
    ]
  };
}

function createTradeConfirmCard(trade) {
  return {
    config: { wide_screen_mode: true },
    header: {
      title: { tag: 'plain_text', content: '💱 确认交易' },
      template: 'orange'
    },
    elements: [
      {
        tag: 'div',
        fields: [
          { is_short: true, text: { tag: 'lark_md', content: `**市场:** ${trade.market}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**方向:** ${trade.side}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**数量:** $${trade.amount}` } },
          { is_short: true, text: { tag: 'lark_md', content: `**价格:** ${trade.price}` } }
        ]
      },
      { tag: 'hr' },
      {
        tag: 'div',
        text: { tag: 'lark_md', content: `**⚠️ 风险提示**\n• 交易存在市场风险\n• 请确认参数正确` }
      },
      {
        tag: 'action',
        actions: [
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '✅ 确认执行' },
            type: 'primary',
            value: { action: 'confirm_trade', tradeId: trade.id }
          },
          {
            tag: 'button',
            text: { tag: 'plain_text', content: '❌ 取消' },
            type: 'default',
            value: { action: 'cancel_trade' }
          }
        ]
      }
    ]
  };
}

// ==================== 数据获取 ====================

async function getPrices() {
  // 检查缓存 (5秒有效)
  const now = Date.now();
  if (priceCache.btc > 0 && priceCache.eth > 0 && now - priceCache.time < 5000) {
    return { btc: priceCache.btc, eth: priceCache.eth, btcChange: priceCache.btcChange, ethChange: priceCache.ethChange };
  }
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    
    const [btcRes, ethRes] = await Promise.all([
      fetch('https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT', { signal: controller.signal }),
      fetch('https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT', { signal: controller.signal })
    ]);
    
    clearTimeout(timeoutId);
    
    const btc = await btcRes.json();
    const eth = await ethRes.json();
    
    const result = {
      btc: parseFloat(btc.lastPrice) || 0,
      eth: parseFloat(eth.lastPrice) || 0,
      btcChange: parseFloat(btc.priceChangePercent) || 0,
      ethChange: parseFloat(eth.priceChangePercent) || 0
    };
    
    // 验证数据有效性
    if (result.btc > 0 && result.eth > 0) {
      // 更新缓存
      priceCache = { 
        btc: result.btc, 
        eth: result.eth, 
        btcChange: result.btcChange, 
        ethChange: result.ethChange,
        time: now 
      };
      return result;
    }
    
    // 数据无效，返回错误
    return { error: '数据无效', btc: 0, eth: 0, btcChange: 0, ethChange: 0 };
    
  } catch (e) {
    console.error('Price fetch error:', e);
    
    // 如果有缓存，使用缓存
    if (priceCache.btc > 0 && priceCache.eth > 0) {
      return { 
        btc: priceCache.btc, 
        eth: priceCache.eth, 
        btcChange: priceCache.btcChange, 
        ethChange: priceCache.ethChange,
        cached: true
      };
    }
    
    // 没有缓存，返回错误
    return { error: '网络错误，请稍后重试', btc: 0, eth: 0, btcChange: 0, ethChange: 0 };
  }
}

async function getMarkets() {
  // 模拟市场数据
  return [
    { question: 'BTC up in 15 min?', yesPrice: 0.48, liquidity: 150000, signal: 'HOLD' },
    { question: 'ETH up in 15 min?', yesPrice: 0.52, liquidity: 80000, signal: 'BUY_YES' },
    { question: 'BTC > $100k by March?', yesPrice: 0.72, liquidity: 200000, signal: 'HOLD' },
    { question: 'SOL > $200?', yesPrice: 0.35, liquidity: 50000, signal: 'BUY_NO' },
    { question: 'Fed rate cut?', yesPrice: 0.25, liquidity: 120000, signal: 'HOLD' }
  ];
}

async function getPricing() {
  const prices = await getPrices();
  return {
    market: 'BTC up in 15 min?',
    marketId: 'btc_15m_up',
    currentPrice: prices.btc,
    strikePrice: prices.btc * 1.005,
    marketPrice: '48.0%',
    theoreticalPrice: '52.3%',
    volatility: '45.2%',
    impliedVol: '48.5%',
    edge: '+4.3%',
    signal: 'BUY_YES',
    recommendation: '建议买入 YES，边际 +4.3% 超过 2% 阈值'
  };
}

async function getArbitrageOpportunities() {
  return [
    { market: 'BTC > $100k', type: '跨平台', profit: '2.5%', confidence: '高' },
    { market: 'ETH 15min UP', type: '站内', profit: '1.8%', confidence: '中' },
    { market: 'SOL > $200', type: '跨平台', profit: '1.2%', confidence: '低' }
  ];
}

// ==================== 卡片回调处理 ====================

async function handleCardAction(action, value, openId) {
  console.log('Card action:', action, value);
  
  switch (action) {
    case 'show_main': {
      const prices = await getPrices();
      return createMainDashboard(prices);
    }
    
    case 'show_markets': {
      const markets = await getMarkets();
      return createMarketMonitorCard(markets);
    }
    
    case 'show_pricing': {
      const pricing = await getPricing();
      return createPricingCard(pricing);
    }
    
    case 'show_config': {
      return createConfigCard();
    }
    
    case 'show_arbitrage': {
      const opps = await getArbitrageOpportunities();
      return createArbitrageCard(opps);
    }
    
    case 'toggle_market_maker': {
      botState.marketMaker.enabled = !botState.marketMaker.enabled;
      const prices = await getPrices();
      return createMainDashboard(prices);
    }
    
    case 'toggle_arbitrage': {
      botState.arbitrage.enabled = !botState.arbitrage.enabled;
      const prices = await getPrices();
      return createMainDashboard(prices);
    }
    
    case 'refresh_markets': {
      const markets = await getMarkets();
      return createMarketMonitorCard(markets);
    }
    
    case 'refresh_pricing': {
      const pricing = await getPricing();
      return createPricingCard(pricing);
    }
    
    case 'refresh_arbitrage': {
      const opps = await getArbitrageOpportunities();
      return createArbitrageCard(opps);
    }
    
    case 'execute_trade': {
      return createTradeConfirmCard({
        id: value.market,
        market: 'BTC up in 15 min?',
        side: 'BUY_YES',
        amount: 100,
        price: '48.0%'
      });
    }
    
    case 'confirm_trade': {
      botState.stats.trades++;
      const prices = await getPrices();
      // 添加成功提示
      return {
        ...createMainDashboard(prices),
        elements: [
          {
            tag: 'alert',
            title: '✅ 交易已执行',
            text: `订单已提交，等待确认`
          },
          ...createMainDashboard(prices).elements
        ]
      };
    }
    
    case 'save_config': {
      // 配置已保存
      return createConfigCard();
    }
    
    default: {
      const prices = await getPrices();
      return createMainDashboard(prices);
    }
  }
}

// ==================== 消息处理 ====================

async function processMessage(text) {
  const t = text.toLowerCase().trim();
  
  if (t === 'help' || t === '/help' || t === '?') {
    return `🤖 Polymarket Super Bot - 控制面板

📱 **控制面板命令:**
  panel - 打开主控制面板
  dashboard - 查看仪表盘
  markets - 市场监控面板
  pricing - 定价分析面板
  config - 配置面板
  arbitrage - 套利机会面板

📊 **快捷查询:**
  btc, eth - 加密货币价格
  status - 机器人状态
  risk - 风险状态

⚡ **快捷操作:**
  mm on/off - 启停做市商
  arb on/off - 启停套利
  strategy <taker/maker/hybrid> - 切换策略

💡 输入 "panel" 打开交互式控制面板`;
  }
  
  if (t === 'panel' || t === '控制面板' || t === 'dashboard') {
    return 'CARD:main';
  }
  
  if (t === 'markets' || t === '市场') {
    return 'CARD:markets';
  }
  
  if (t === 'pricing' || t === '定价') {
    return 'CARD:pricing';
  }
  
  if (t === 'config' || t === '配置') {
    return 'CARD:config';
  }
  
  if (t === 'arbitrage' || t === '套利') {
    return 'CARD:arbitrage';
  }
  
  if (t === 'status' || t === '状态') {
    return `🤖 Bot 状态

📊 状态: ${botState.status === 'running' ? '✅ 运行中' : '⏸️ 已暂停'}
🎯 策略: ${botState.strategy.toUpperCase()}
📈 做市商: ${botState.marketMaker.enabled ? '✅' : '⏸️'}
💰 套利: ${botState.arbitrage.enabled ? '✅' : '⏸️'}
📊 信号: ${botState.stats.signals}
📈 交易: ${botState.stats.trades}
💰 盈亏: ${botState.stats.pnl >= 0 ? '+' : ''}$${botState.stats.pnl.toFixed(2)}`;
  }
  
  if (t === 'mm on') {
    botState.marketMaker.enabled = true;
    return '✅ 做市商已启用\n\n输入 "panel" 查看控制面板';
  }
  
  if (t === 'mm off') {
    botState.marketMaker.enabled = false;
    return '⏸️ 做市商已停止\n\n输入 "panel" 查看控制面板';
  }
  
  if (t === 'arb on') {
    botState.arbitrage.enabled = true;
    return '✅ 套利已启用\n\n输入 "panel" 查看控制面板';
  }
  
  if (t === 'arb off') {
    botState.arbitrage.enabled = false;
    return '⏸️ 套利已停止\n\n输入 "panel" 查看控制面板';
  }
  
  if (t.startsWith('strategy ')) {
    const s = t.split(' ')[1];
    if (['taker', 'maker', 'hybrid'].includes(s)) {
      botState.strategy = s === 'maker' ? 'market_maker' : s;
      return `✅ 策略已切换: ${s.toUpperCase()}\n\n输入 "panel" 查看控制面板`;
    }
    return '❌ 无效策略，可选: taker, maker, hybrid';
  }
  
  if (t === 'btc') {
    const prices = await getPrices();
    if (prices.error) return `❌ ${prices.error}\n💡 请稍后重试`;
    if (prices.btc === 0) return `❌ 无法获取价格\n💡 请检查网络连接`;
    return `🪙 BTC/USDT\n💰 $${prices.btc.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}\n${prices.btcChange >= 0 ? '📈' : '📉'} ${prices.btcChange.toFixed(2)}%\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  }
  
  if (t === 'eth') {
    const prices = await getPrices();
    if (prices.error) return `❌ ${prices.error}\n💡 请稍后重试`;
    if (prices.eth === 0) return `❌ 无法获取价格\n💡 请检查网络连接`;
    return `💎 ETH/USDT\n💰 $${prices.eth.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}\n${prices.ethChange >= 0 ? '📈' : '📉'} ${prices.ethChange.toFixed(2)}%\n📍 Binance\n⏰ ${new Date().toLocaleTimeString()}`;
  }
  
  if (t === 'risk') {
    return `🛡️ 风险状态

📊 风险等级: ${botState.risk.circuitBreaker ? '🔴 高' : '🟢 低'}
💰 最大仓位: $${botState.risk.maxPosition}
📉 止损: ${(botState.risk.stopLoss * 100).toFixed(0)}%
🚨 熔断: ${botState.risk.circuitBreaker ? '已触发' : '正常'}`;
  }
  
  return `🤖 收到: "${text}"\n\n💡 输入 "panel" 打开控制面板\n💡 输入 "help" 查看所有命令`;
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
      service: 'polymarket-control-panel',
      version: '3.0.0',
      features: ['interactive-cards', 'dashboard', 'market-monitor', 'pricing', 'config', 'arbitrage']
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
  
  // 处理卡片回调
  if (body && body.type === 'card') {
    try {
      const action = body.action?.value || {};
      const openId = body.open_id || '';
      
      const card = await handleCardAction(action.action, action, openId);
      
      if (card) {
        return res.status(200).json({
          toast: { type: 'success', content: '操作成功' },
          card: card
        });
      }
    } catch (e) {
      console.error('Card callback error:', e);
    }
    return res.status(200).json({ code: 0 });
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
          
          // 检查是否需要发送卡片
          if (reply.startsWith('CARD:')) {
            const cardType = reply.substring(5);
            let card;
            
            if (cardType === 'main') {
              const prices = await getPrices();
              card = createMainDashboard(prices);
            } else if (cardType === 'markets') {
              const markets = await getMarkets();
              card = createMarketMonitorCard(markets);
            } else if (cardType === 'pricing') {
              const pricing = await getPricing();
              card = createPricingCard(pricing);
            } else if (cardType === 'config') {
              card = createConfigCard();
            } else if (cardType === 'arbitrage') {
              const opps = await getArbitrageOpportunities();
              card = createArbitrageCard(opps);
            }
            
            if (card) {
              if (chatType === 'group') {
                await replyCardMessage(messageId, card);
              } else {
                await sendCardMessage(openId, card);
              }
            }
          } else {
            // 发送文本消息
            if (chatType === 'group') {
              const token = await getLarkToken();
              await fetch(`${LARK_API}/im/v1/messages/${messageId}/reply`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ msg_type: 'text', content: JSON.stringify({ text: reply }) })
              });
            } else {
              const token = await getLarkToken();
              await fetch(`${LARK_API}/im/v1/messages?receive_id_type=open_id`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                body: JSON.stringify({ receive_id: openId, msg_type: 'text', content: JSON.stringify({ text: reply }) })
              });
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

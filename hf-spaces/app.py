"""
Polymarket Arbitrage Simulator - 模拟测试环境

完全模拟测试，无需真实私钥
测试套利策略、定价模型、风险管理
"""
import os
import json
import asyncio
import logging
import time
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')

import gradio as gr
import httpx

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
log = logging.getLogger(__name__)

# ==================== 配置 ====================

@dataclass
class SimulationConfig:
    """模拟测试配置"""
    # 资金配置
    initial_capital: float = 1000.0      # 初始资金 USDC
    max_position_size: float = 100.0     # 单笔最大仓位
    max_daily_loss: float = 100.0        # 每日最大亏损
    max_drawdown: float = 0.20           # 最大回撤 20%
    
    # 套利配置
    min_profit_pct: float = 0.02         # 最小利润 2%
    min_similarity: float = 0.78         # 最小相似度
    max_slippage_bps: int = 250          # 最大滑点 2.5%
    fee_bps: int = 100                   # 手续费 1%
    
    # 风控配置
    stop_loss_pct: float = 0.30          # 止损 30%
    take_profit_pct: float = 0.20        # 止盈 20%
    circuit_breaker_threshold: float = 0.10  # 熔断阈值 10%
    
    # 模拟配置
    simulation_speed: float = 1.0        # 模拟速度倍数
    price_volatility: float = 0.02       # 价格波动率
    market_count: int = 20               # 模拟市场数量
    
    # 开关
    cross_platform_enabled: bool = True
    intra_platform_enabled: bool = True
    auto_execute: bool = False           # 自动执行（模拟中）


@dataclass
class Market:
    """模拟市场"""
    market_id: str
    question: str
    platform: str
    yes_price: float
    no_price: float
    liquidity: float
    volume_24h: float
    strike_price: float
    expiry_minutes: int
    current_underlying_price: float
    volatility: float = 0.45
    bid: float = 0.0
    ask: float = 0.0
    
    def __post_init__(self):
        self.bid = self.yes_price - 0.01
        self.ask = self.yes_price + 0.01


@dataclass
class Trade:
    """交易记录"""
    trade_id: str
    timestamp: float
    market_id: str
    platform: str
    side: str  # BUY_YES, BUY_NO, SELL_YES, SELL_NO
    size: float
    price: float
    theoretical_price: float
    edge: float
    pnl: float = 0.0
    status: str = "filled"


@dataclass
class Position:
    """持仓"""
    market_id: str
    platform: str
    side: str  # YES or NO
    size: float
    entry_price: float
    current_price: float
    pnl: float = 0.0
    pnl_pct: float = 0.0
    
    def update_price(self, new_price: float):
        self.current_price = new_price
        if self.side == "YES":
            self.pnl = self.size * (new_price - self.entry_price)
        else:
            self.pnl = self.size * ((1 - new_price) - (1 - self.entry_price))
        self.pnl_pct = self.pnl / (self.size * self.entry_price) if self.entry_price > 0 else 0


@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    opportunity_id: str
    type: str  # cross_platform, intra_platform
    market_a: Market
    market_b: Optional[Market]
    profit_pct: float
    profit_usd: float
    action: str
    confidence: float
    timestamp: float


# ==================== 模拟器 ====================

class ArbitrageSimulator:
    """套利模拟器"""
    
    def __init__(self, config: SimulationConfig = None):
        self.config = config or SimulationConfig()
        
        # 状态
        self.capital = self.config.initial_capital
        self.initial_capital = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.opportunities: List[ArbitrageOpportunity] = []
        
        # 市场
        self.markets: Dict[str, Market] = {}
        self.price_history: Dict[str, List[float]] = {}
        
        # 统计
        self.stats = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "win_rate": 0.0,
            "avg_profit": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
        }
        
        # 初始化市场
        self._init_markets()
        
        # 缓存
        self._price_cache = {}
        
    def _init_markets(self):
        """初始化模拟市场"""
        base_prices = {
            "BTC": 64000 + random.uniform(-2000, 2000),
            "ETH": 1850 + random.uniform(-100, 100),
            "SOL": 140 + random.uniform(-10, 10),
        }
        
        market_templates = [
            # Polymarket 市场
            {"question": "BTC above ${price} in {time}min?", "underlying": "BTC", "platform": "Polymarket"},
            {"question": "ETH above ${price} in {time}min?", "underlying": "ETH", "platform": "Polymarket"},
            {"question": "SOL above ${price} in {time}min?", "underlying": "SOL", "platform": "Polymarket"},
            {"question": "BTC up in next {time} min?", "underlying": "BTC", "platform": "Polymarket"},
            {"question": "ETH up in next {time} min?", "underlying": "ETH", "platform": "Polymarket"},
            # Predict.fun 市场（相似但不同平台）
            {"question": "Will BTC exceed ${price} in {time}min?", "underlying": "BTC", "platform": "Predict.fun"},
            {"question": "Will ETH exceed ${price} in {time}min?", "underlying": "ETH", "platform": "Predict.fun"},
            {"question": "BTC price increase in {time}min?", "underlying": "BTC", "platform": "Predict.fun"},
            {"question": "ETH price increase in {time}min?", "underlying": "ETH", "platform": "Predict.fun"},
            # Probable 市场
            {"question": "Bitcoin > ${price} in {time} minutes?", "underlying": "BTC", "platform": "Probable"},
            {"question": "Ethereum > ${price} in {time} minutes?", "underlying": "ETH", "platform": "Probable"},
        ]
        
        timeframes = [5, 10, 15, 30, 60]
        market_id = 0
        
        for template in market_templates:
            for tf in timeframes[:3]:  # 只用前3个时间框架
                underlying = template["underlying"]
                base_price = base_prices[underlying]
                
                # 计算行权价
                strike_multiplier = 1 + random.uniform(0.001, 0.02) * (tf / 15)
                strike_price = base_price * strike_multiplier
                
                # 生成价格（基于 BS 模型模拟）
                T = tf / (365 * 24 * 60)  # 年化时间
                sigma = random.uniform(0.4, 0.6)
                theoretical_price = self._price_binary_option(base_price, strike_price, T, 0.05, sigma)
                
                # 添加市场噪音
                noise = random.uniform(-0.03, 0.03)
                yes_price = max(0.05, min(0.95, theoretical_price + noise))
                
                question = template["question"].format(
                    price=int(strike_price),
                    time=tf
                )
                
                market = Market(
                    market_id=f"mkt_{market_id:03d}",
                    question=question,
                    platform=template["platform"],
                    yes_price=yes_price,
                    no_price=1 - yes_price,
                    liquidity=random.uniform(50000, 500000),
                    volume_24h=random.uniform(10000, 100000),
                    strike_price=strike_price,
                    expiry_minutes=tf,
                    current_underlying_price=base_price,
                    volatility=sigma
                )
                
                self.markets[market.market_id] = market
                self.price_history[market.market_id] = [yes_price]
                market_id += 1
                
                if market_id >= self.config.market_count:
                    break
            
            if market_id >= self.config.market_count:
                break
        
        log.info(f"初始化 {len(self.markets)} 个模拟市场")
    
    def _price_binary_option(self, S: float, K: float, T: float, r: float = 0.05, sigma: float = 0.5) -> float:
        """Black-Scholes 二元期权定价"""
        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            return 0.5
        
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        
        # 使用标准正态分布 CDF
        def norm_cdf(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))
        
        price = math.exp(-r * T) * norm_cdf(d2)
        return max(0.0, min(1.0, price))
    
    def update_prices(self):
        """更新市场价格（模拟价格变动）"""
        for market_id, market in self.markets.items():
            # 随机游走
            change = random.gauss(0, self.config.price_volatility / 10)
            market.yes_price = max(0.05, min(0.95, market.yes_price + change))
            market.no_price = 1 - market.yes_price
            market.bid = market.yes_price - random.uniform(0.005, 0.015)
            market.ask = market.yes_price + random.uniform(0.005, 0.015)
            
            # 记录历史
            self.price_history[market_id].append(market.yes_price)
            if len(self.price_history[market_id]) > 100:
                self.price_history[market_id] = self.price_history[market_id][-100:]
            
            # 更新持仓价格
            if market_id in self.positions:
                self.positions[market_id].update_price(market.yes_price)
    
    def scan_arbitrage(self) -> List[ArbitrageOpportunity]:
        """扫描套利机会"""
        opportunities = []
        
        # 1. 跨平台套利
        if self.config.cross_platform_enabled:
            opportunities.extend(self._scan_cross_platform())
        
        # 2. 站内套利 (Yes + No != 1)
        if self.config.intra_platform_enabled:
            opportunities.extend(self._scan_intra_platform())
        
        # 按利润排序
        opportunities.sort(key=lambda x: x.profit_pct, reverse=True)
        
        self.opportunities = opportunities[:20]  # 保留前20个
        return self.opportunities
    
    def _scan_cross_platform(self) -> List[ArbitrageOpportunity]:
        """扫描跨平台套利"""
        opportunities = []
        markets_list = list(self.markets.values())
        
        for i, m1 in enumerate(markets_list):
            for m2 in markets_list[i+1:]:
                # 检查是否是相似市场（不同平台）
                if m1.platform == m2.platform:
                    continue
                
                # 计算相似度（简化：基于行权价）
                price_diff = abs(m1.strike_price - m2.strike_price) / max(m1.strike_price, m2.strike_price)
                time_diff = abs(m1.expiry_minutes - m2.expiry_minutes) / max(m1.expiry_minutes, m2.expiry_minutes)
                
                similarity = 1 - (price_diff + time_diff) / 2
                
                if similarity >= self.config.min_similarity:
                    # 检查价差
                    price_gap = abs(m1.yes_price - m2.yes_price)
                    
                    # 扣除手续费和滑点
                    total_cost = (self.config.fee_bps / 10000) * 2 + (self.config.max_slippage_bps / 10000) * 2
                    profit_pct = price_gap - total_cost
                    
                    if profit_pct >= self.config.min_profit_pct:
                        position_size = min(self.config.max_position_size, self.capital * 0.1)
                        profit_usd = position_size * profit_pct
                        
                        opp = ArbitrageOpportunity(
                            opportunity_id=f"arb_{len(opportunities):03d}",
                            type="cross_platform",
                            market_a=m1,
                            market_b=m2,
                            profit_pct=profit_pct,
                            profit_usd=profit_usd,
                            action=f"BUY {m1.market_id} @ {m1.yes_price:.2%}, SELL {m2.market_id} @ {m2.yes_price:.2%}" if m1.yes_price < m2.yes_price else f"BUY {m2.market_id} @ {m2.yes_price:.2%}, SELL {m1.market_id} @ {m1.yes_price:.2%}",
                            confidence=similarity,
                            timestamp=time.time()
                        )
                        opportunities.append(opp)
        
        return opportunities
    
    def _scan_intra_platform(self) -> List[ArbitrageOpportunity]:
        """扫描站内套利 (Yes + No != 1)"""
        opportunities = []
        
        for market_id, market in self.markets.items():
            # Yes + No 应该等于 1
            total = market.yes_price + market.no_price
            deviation = abs(total - 1)
            
            # 扣除成本
            total_cost = (self.config.fee_bps / 10000) * 2
            profit_pct = deviation - total_cost
            
            if profit_pct >= self.config.min_profit_pct:
                position_size = min(self.config.max_position_size, self.capital * 0.1)
                profit_usd = position_size * profit_pct
                
                opp = ArbitrageOpportunity(
                    opportunity_id=f"intra_{market_id}",
                    type="intra_platform",
                    market_a=market,
                    market_b=None,
                    profit_pct=profit_pct,
                    profit_usd=profit_usd,
                    action=f"同时买入 YES @ {market.yes_price:.2%} 和 NO @ {market.no_price:.2%}，总成本 {total:.2%}",
                    confidence=0.95,  # 站内套利置信度较高
                    timestamp=time.time()
                )
                opportunities.append(opp)
        
        return opportunities
    
    def execute_trade(self, opportunity: ArbitrageOpportunity, size: float = None) -> Trade:
        """执行交易"""
        if size is None:
            size = min(self.config.max_position_size, self.capital * 0.1)
        
        size = min(size, self.capital * 0.2)  # 最大使用20%资金
        
        if size > self.capital:
            return None  # 资金不足
        
        m1 = opportunity.market_a
        
        # 模拟滑点
        slippage = random.uniform(0, self.config.max_slippage_bps / 10000)
        fill_price = m1.ask + slippage
        
        # 创建交易记录
        trade = Trade(
            trade_id=f"trade_{len(self.trades):05d}",
            timestamp=time.time(),
            market_id=m1.market_id,
            platform=m1.platform,
            side="BUY_YES",
            size=size,
            price=fill_price,
            theoretical_price=m1.yes_price,
            edge=opportunity.profit_pct,
            status="filled"
        )
        
        # 更新资金和持仓
        cost = size * fill_price
        self.capital -= cost
        
        position = Position(
            market_id=m1.market_id,
            platform=m1.platform,
            side="YES",
            size=size,
            entry_price=fill_price,
            current_price=m1.yes_price
        )
        
        self.positions[m1.market_id] = position
        self.trades.append(trade)
        self.stats["total_trades"] += 1
        
        log.info(f"执行交易: {trade.trade_id} | 市场: {m1.question[:30]}... | 价格: {fill_price:.2%} | 数量: ${size:.2f}")
        
        return trade
    
    def close_position(self, market_id: str) -> Optional[Trade]:
        """平仓"""
        if market_id not in self.positions:
            return None
        
        position = self.positions[market_id]
        market = self.markets.get(market_id)
        
        if not market:
            return None
        
        # 计算盈亏
        sell_price = market.bid - random.uniform(0, 0.005)  # 滑点
        proceeds = position.size * sell_price
        pnl = proceeds - (position.size * position.entry_price)
        
        # 更新资金
        self.capital += proceeds
        
        # 创建平仓交易
        trade = Trade(
            trade_id=f"trade_{len(self.trades):05d}",
            timestamp=time.time(),
            market_id=market_id,
            platform=position.platform,
            side="SELL_YES",
            size=position.size,
            price=sell_price,
            theoretical_price=market.yes_price,
            edge=0,
            pnl=pnl,
            status="filled"
        )
        
        self.trades.append(trade)
        
        # 更新统计
        if pnl > 0:
            self.stats["winning_trades"] += 1
        else:
            self.stats["losing_trades"] += 1
        
        self.stats["total_pnl"] += pnl
        
        # 删除持仓
        del self.positions[market_id]
        
        log.info(f"平仓: {trade.trade_id} | 盈亏: ${pnl:+.2f}")
        
        return trade
    
    def run_simulation(self, steps: int = 100, auto_trade: bool = False) -> Dict:
        """运行模拟"""
        log.info(f"开始模拟 {steps} 步, 自动交易: {auto_trade}")
        
        results = {
            "initial_capital": self.initial_capital,
            "final_capital": 0,
            "total_pnl": 0,
            "trades": [],
            "opportunities_found": 0,
            "trades_executed": 0,
            "win_rate": 0,
            "max_drawdown": 0,
        }
        
        peak_capital = self.capital
        max_drawdown = 0
        
        for step in range(steps):
            # 更新价格
            self.update_prices()
            
            # 扫描机会
            opps = self.scan_arbitrage()
            results["opportunities_found"] += len(opps)
            
            # 自动交易
            if auto_trade and opps:
                best_opp = opps[0]
                if best_opp.profit_pct >= self.config.min_profit_pct:
                    self.execute_trade(best_opp)
                    results["trades_executed"] += 1
            
            # 随机平仓（模拟到期）
            for market_id in list(self.positions.keys()):
                if random.random() < 0.05:  # 5% 概率平仓
                    self.close_position(market_id)
            
            # 更新最大回撤
            if self.capital > peak_capital:
                peak_capital = self.capital
            drawdown = (peak_capital - self.capital) / peak_capital
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # 检查熔断
            if drawdown >= self.config.circuit_breaker_threshold:
                log.warning(f"熔断触发! 回撤: {drawdown:.2%}")
                break
        
        # 平掉所有持仓
        for market_id in list(self.positions.keys()):
            self.close_position(market_id)
        
        # 计算最终结果
        results["final_capital"] = self.capital
        results["total_pnl"] = self.capital - self.initial_capital
        results["max_drawdown"] = max_drawdown
        results["trades"] = [
            {
                "id": t.trade_id,
                "market": t.market_id,
                "side": t.side,
                "price": f"{t.price:.2%}",
                "size": f"${t.size:.2f}",
                "pnl": f"${t.pnl:+.2f}"
            }
            for t in self.trades[-20:]  # 最近20笔
        ]
        
        if self.stats["total_trades"] > 0:
            results["win_rate"] = self.stats["winning_trades"] / self.stats["total_trades"]
        
        return results
    
    def get_status(self) -> Dict:
        """获取当前状态"""
        total_pnl = sum(p.pnl for p in self.positions.values())
        
        return {
            "capital": f"${self.capital:,.2f}",
            "positions": len(self.positions),
            "total_trades": self.stats["total_trades"],
            "total_pnl": f"${self.capital - self.initial_capital:+,.2f}",
            "winning_trades": self.stats["winning_trades"],
            "losing_trades": self.stats["losing_trades"],
            "opportunities": len(self.opportunities),
            "markets_tracked": len(self.markets),
        }
    
    def get_opportunities_table(self) -> List[List]:
        """获取套利机会表格"""
        return [
            [
                o.type,
                o.market_a.question[:25] + "...",
                f"{o.profit_pct:.2%}",
                f"${o.profit_usd:.2f}",
                f"{o.confidence:.0%}",
                o.market_a.platform
            ]
            for o in self.opportunities[:10]
        ]
    
    def get_positions_table(self) -> List[List]:
        """获取持仓表格"""
        return [
            [
                p.market_id,
                p.platform,
                p.side,
                f"${p.size:.2f}",
                f"{p.entry_price:.2%}",
                f"{p.current_price:.2%}",
                f"${p.pnl:+.2f}",
                f"{p.pnl_pct:+.2%}"
            ]
            for p in self.positions.values()
        ]
    
    def reset(self):
        """重置模拟器"""
        self.capital = self.config.initial_capital
        self.positions.clear()
        self.trades.clear()
        self.opportunities.clear()
        self.stats = {k: 0 for k in self.stats}
        self._init_markets()
        log.info("模拟器已重置")


# ==================== 创建模拟器实例 ====================

simulator = ArbitrageSimulator()


# ==================== Gradio 界面 ====================

def format_result(result: Dict) -> str:
    """格式化结果"""
    return json.dumps(result, indent=2, ensure_ascii=False)


with gr.Blocks(title="Polymarket 套利模拟器", theme=gr.themes.Soft()) as demo:
    
    gr.Markdown("""
    # 🧪 Polymarket 套利模拟器
    
    **完全模拟测试，无需真实私钥**
    
    测试套利策略、定价模型、风险管理
    """)
    
    with gr.Tabs():
        # Tab 1: 控制面板
        with gr.TabItem("📊 控制面板"):
            status_output = gr.Code(label="当前状态", language="json", value=format_result(simulator.get_status()))
            
            with gr.Row():
                refresh_btn = gr.Button("🔄 刷新状态", variant="secondary")
                reset_btn = gr.Button("🔃 重置模拟器", variant="secondary")
            
            gr.Markdown("### 套利机会")
            opps_table = gr.Dataframe(
                headers=["类型", "市场", "利润率", "预期收益", "置信度", "平台"],
                value=simulator.get_opportunities_table(),
                label="发现的套利机会"
            )
            scan_btn = gr.Button("🔍 扫描机会", variant="primary")
            
            gr.Markdown("### 当前持仓")
            positions_table = gr.Dataframe(
                headers=["市场ID", "平台", "方向", "数量", "入场价", "当前价", "盈亏", "收益率"],
                value=simulator.get_positions_table(),
                label="持仓列表"
            )
        
        # Tab 2: 模拟测试
        with gr.TabItem("🧪 模拟测试"):
            gr.Markdown("### 运行模拟")
            
            with gr.Row():
                sim_steps = gr.Slider(label="模拟步数", minimum=10, maximum=500, value=100, step=10)
                sim_auto = gr.Checkbox(label="自动交易", value=False)
            
            sim_btn = gr.Button("▶️ 运行模拟", variant="primary", size="lg")
            
            gr.Markdown("### 模拟结果")
            sim_result = gr.Code(label="结果", language="json")
            
            gr.Markdown("### 交易记录")
            trades_output = gr.Dataframe(
                headers=["ID", "市场", "方向", "价格", "数量", "盈亏"],
                value=[]
            )
        
        # Tab 3: 配置
        with gr.TabItem("⚙️ 配置"):
            gr.Markdown("### 资金配置")
            
            with gr.Row():
                cfg_capital = gr.Number(label="初始资金 ($)", value=1000)
                cfg_max_pos = gr.Number(label="单笔最大仓位 ($)", value=100)
                cfg_max_loss = gr.Number(label="每日最大亏损 ($)", value=100)
            
            gr.Markdown("### 套利配置")
            
            with gr.Row():
                cfg_min_profit = gr.Slider(label="最小利润 (%)", minimum=0.5, maximum=5, value=2, step=0.5)
                cfg_similarity = gr.Slider(label="最小相似度 (%)", minimum=50, maximum=95, value=78, step=1)
                cfg_slippage = gr.Slider(label="最大滑点 (基点)", minimum=50, maximum=500, value=250, step=10)
            
            gr.Markdown("### 风控配置")
            
            with gr.Row():
                cfg_stop_loss = gr.Slider(label="止损 (%)", minimum=5, maximum=50, value=30, step=5)
                cfg_take_profit = gr.Slider(label="止盈 (%)", minimum=5, maximum=50, value=20, step=5)
                cfg_circuit = gr.Slider(label="熔断阈值 (%)", minimum=5, maximum=30, value=10, step=1)
            
            gr.Markdown("### 开关")
            
            with gr.Row():
                cfg_cross = gr.Checkbox(label="跨平台套利", value=True)
                cfg_intra = gr.Checkbox(label="站内套利", value=True)
            
            cfg_btn = gr.Button("💾 应用配置", variant="primary")
            cfg_result = gr.Code(label="配置结果", language="json")
        
        # Tab 4: 手动交易
        with gr.TabItem("💱 手动交易"):
            gr.Markdown("### 执行交易")
            
            opp_select = gr.Dropdown(
                label="选择套利机会",
                choices=[],
                interactive=True
            )
            
            trade_size = gr.Number(label="交易金额 ($)", value=100)
            trade_btn = gr.Button("📈 执行交易", variant="primary")
            trade_result = gr.Code(label="交易结果", language="json")
            
            gr.Markdown("### 平仓")
            
            pos_select = gr.Dropdown(
                label="选择持仓",
                choices=[],
                interactive=True
            )
            close_btn = gr.Button("📉 平仓", variant="secondary")
            close_result = gr.Code(label="平仓结果", language="json")
        
        # Tab 5: 分析报告
        with gr.TabItem("📋 分析报告"):
            report_btn = gr.Button("📊 生成报告", variant="primary")
            report_output = gr.Code(label="模拟测试报告", language="json")
    
    # ==================== 事件处理 ====================
    
    def refresh_status():
        return format_result(simulator.get_status())
    
    def reset_simulator():
        simulator.reset()
        return format_result(simulator.get_status())
    
    def scan_opportunities():
        simulator.update_prices()
        opps = simulator.scan_arbitrage()
        return simulator.get_opportunities_table()
    
    def run_simulation(steps, auto_trade):
        result = simulator.run_simulation(int(steps), auto_trade)
        return format_result(result), [
            [t["id"], t["market"], t["side"], t["price"], t["size"], t["pnl"]]
            for t in result.get("trades", [])
        ]
    
    def apply_config(capital, max_pos, max_loss, min_profit, similarity, slippage, 
                     stop_loss, take_profit, circuit, cross, intra):
        simulator.config.initial_capital = capital
        simulator.config.max_position_size = max_pos
        simulator.config.max_daily_loss = max_loss
        simulator.config.min_profit_pct = min_profit / 100
        simulator.config.min_similarity = similarity / 100
        simulator.config.max_slippage_bps = int(slippage)
        simulator.config.stop_loss_pct = stop_loss / 100
        simulator.config.take_profit_pct = take_profit / 100
        simulator.config.circuit_breaker_threshold = circuit / 100
        simulator.config.cross_platform_enabled = cross
        simulator.config.intra_platform_enabled = intra
        
        return format_result({
            "status": "配置已应用",
            "config": asdict(simulator.config)
        })
    
    def update_dropdowns():
        opp_choices = [f"{o.opportunity_id}: {o.profit_pct:.2%}" for o in simulator.opportunities[:10]]
        pos_choices = [f"{p.market_id}: ${p.size:.2f}" for p in simulator.positions.values()]
        return gr.Dropdown(choices=opp_choices), gr.Dropdown(choices=pos_choices)
    
    def execute_selected(opp_str, size):
        if not opp_str:
            return format_result({"error": "请选择套利机会"})
        
        opp_id = opp_str.split(":")[0]
        opp = next((o for o in simulator.opportunities if o.opportunity_id == opp_id), None)
        
        if not opp:
            return format_result({"error": "未找到套利机会"})
        
        trade = simulator.execute_trade(opp, size)
        if trade:
            return format_result({
                "status": "交易成功",
                "trade_id": trade.trade_id,
                "market": trade.market_id,
                "side": trade.side,
                "price": f"{trade.price:.2%}",
                "size": f"${trade.size:.2f}",
                "edge": f"{trade.edge:.2%}"
            })
        return format_result({"error": "交易失败"})
    
    def close_selected(pos_str):
        if not pos_str:
            return format_result({"error": "请选择持仓"})
        
        market_id = pos_str.split(":")[0]
        trade = simulator.close_position(market_id)
        
        if trade:
            return format_result({
                "status": "平仓成功",
                "trade_id": trade.trade_id,
                "pnl": f"${trade.pnl:+.2f}"
            })
        return format_result({"error": "平仓失败"})
    
    def generate_report():
        total_pnl = simulator.capital - simulator.initial_capital
        win_rate = simulator.stats["winning_trades"] / max(1, simulator.stats["total_trades"]) * 100
        
        return format_result({
            "模拟测试报告": {
                "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "初始资金": f"${simulator.initial_capital:,.2f}",
                "最终资金": f"${simulator.capital:,.2f}",
                "总盈亏": f"${total_pnl:+,.2f}",
                "收益率": f"{total_pnl / simulator.initial_capital:+.2%}",
            },
            "交易统计": {
                "总交易次数": simulator.stats["total_trades"],
                "盈利次数": simulator.stats["winning_trades"],
                "亏损次数": simulator.stats["losing_trades"],
                "胜率": f"{win_rate:.1f}%",
            },
            "当前状态": {
                "持仓数": len(simulator.positions),
                "可套利机会": len(simulator.opportunities),
                "监控市场": len(simulator.markets),
            },
            "配置参数": {
                "最小利润": f"{simulator.config.min_profit_pct:.1%}",
                "最大仓位": f"${simulator.config.max_position_size}",
                "止损": f"{simulator.config.stop_loss_pct:.0%}",
                "止盈": f"{simulator.config.take_profit_pct:.0%}",
            }
        })
    
    # 绑定事件
    refresh_btn.click(refresh_status, outputs=status_output)
    reset_btn.click(reset_simulator, outputs=status_output)
    scan_btn.click(scan_opportunities, outputs=opps_table)
    
    sim_btn.click(run_simulation, inputs=[sim_steps, sim_auto], outputs=[sim_result, trades_output])
    
    cfg_btn.click(apply_config, 
        inputs=[cfg_capital, cfg_max_pos, cfg_max_loss, cfg_min_profit, cfg_similarity, cfg_slippage,
                cfg_stop_loss, cfg_take_profit, cfg_circuit, cfg_cross, cfg_intra],
        outputs=cfg_result)
    
    scan_btn.click(update_dropdowns, outputs=[opp_select, pos_select])
    
    trade_btn.click(execute_selected, inputs=[opp_select, trade_size], outputs=trade_result)
    close_btn.click(close_selected, inputs=[pos_select], outputs=close_result)
    
    report_btn.click(generate_report, outputs=report_output)


# ==================== FastAPI ====================

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="Polymarket Arbitrage Simulator")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "polymarket-arbitrage-simulator",
        "mode": "simulation",
        "capital": simulator.capital,
        "positions": len(simulator.positions),
        "markets": len(simulator.markets)
    }


@app.get("/api/opportunities")
async def api_opportunities():
    simulator.update_prices()
    opps = simulator.scan_arbitrage()
    return [
        {
            "id": o.opportunity_id,
            "type": o.type,
            "market": o.market_a.question,
            "profit_pct": f"{o.profit_pct:.2%}",
            "profit_usd": f"${o.profit_usd:.2f}",
            "confidence": f"{o.confidence:.0%}",
            "platform": o.market_a.platform
        }
        for o in opps[:10]
    ]


@app.get("/api/status")
async def api_status():
    return simulator.get_status()


app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

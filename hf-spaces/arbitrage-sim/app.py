"""
Polymarket Arbitrage Simulator - 模拟测试环境

完全模拟测试，无需真实私钥
测试套利策略、定价模型、风险管理
"""
import os
import json
import time
import math
import random
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import gradio as gr

# ==================== 配置 ====================

@dataclass
class Config:
    initial_capital: float = 1000.0
    max_position: float = 100.0
    min_profit: float = 0.02  # 2%
    stop_loss: float = 0.30   # 30%
    take_profit: float = 0.20 # 20%
    fee_bps: int = 100        # 1%

# ==================== 模拟市场 ====================

@dataclass
class Market:
    id: str
    question: str
    platform: str
    yes: float
    no: float
    strike: float
    underlying: str
    
    def update(self):
        delta = random.gauss(0, 0.005)
        self.yes = max(0.05, min(0.95, self.yes + delta))
        self.no = 1 - self.yes

# ==================== 模拟器 ====================

class Simulator:
    def __init__(self):
        self.cfg = Config()
        self.capital = self.cfg.initial_capital
        self.positions: Dict = {}
        self.trades: List = []
        self.markets: Dict[str, Market] = {}
        self.opps: List = []
        self.stats = {"trades": 0, "wins": 0, "pnl": 0}
        self._init_markets()
    
    def _init_markets(self):
        base = {"BTC": 64000, "ETH": 1850}
        platforms = ["Polymarket", "Predict.fun", "Probable"]
        
        mid = 0
        for p in platforms:
            for u, price in base.items():
                for tf in [5, 10, 15]:
                    strike = price * (1 + random.uniform(0.001, 0.02))
                    yes = random.uniform(0.3, 0.7)
                    self.markets[f"m{mid}"] = Market(
                        id=f"m{mid}",
                        question=f"{u} above ${int(strike)} in {tf}min?",
                        platform=p,
                        yes=yes,
                        no=1-yes,
                        strike=strike,
                        underlying=u
                    )
                    mid += 1
    
    def update_prices(self):
        for m in self.markets.values():
            m.update()
        for pid, pos in self.positions.items():
            m = self.markets.get(pid)
            if m:
                pos["current"] = m.yes
                pos["pnl"] = pos["size"] * (m.yes - pos["entry"])
    
    def scan(self) -> List:
        """扫描套利机会"""
        opps = []
        mkts = list(self.markets.values())
        
        # 跨平台
        for i, m1 in enumerate(mkts):
            for m2 in mkts[i+1:]:
                if m1.platform == m2.platform:
                    continue
                gap = abs(m1.yes - m2.yes)
                cost = self.cfg.fee_bps / 5000
                if gap > cost + self.cfg.min_profit:
                    opps.append({
                        "type": "跨平台",
                        "m1": m1.id,
                        "m2": m2.id,
                        "profit": f"{(gap-cost)*100:.1f}%",
                        "action": f"买 {m1.platform} 卖 {m2.platform}"
                    })
        
        # 站内 (Yes+No != 1)
        for m in mkts:
            gap = abs(m.yes + m.no - 1)
            cost = self.cfg.fee_bps / 2500
            if gap > cost + self.cfg.min_profit:
                opps.append({
                    "type": "站内",
                    "m1": m.id,
                    "m2": None,
                    "profit": f"{(gap-cost)*100:.1f}%",
                    "action": f"同时买 YES+NO @ {m.platform}"
                })
        
        opps.sort(key=lambda x: x["profit"], reverse=True)
        self.opps = opps[:10]
        return self.opps
    
    def trade(self, market_id: str, size: float = None) -> Dict:
        """执行交易"""
        m = self.markets.get(market_id)
        if not m:
            return {"error": "市场不存在"}
        
        if size is None:
            size = min(self.cfg.max_position, self.capital * 0.1)
        
        if size > self.capital:
            return {"error": "资金不足"}
        
        fill = m.yes + random.uniform(0, 0.005)
        self.capital -= size * fill
        
        self.positions[market_id] = {
            "market": m.question[:25],
            "platform": m.platform,
            "size": size,
            "entry": fill,
            "current": m.yes,
            "pnl": 0
        }
        
        self.trades.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "market": m.question[:20],
            "price": f"{fill:.1%}",
            "size": f"${size:.0f}"
        })
        self.stats["trades"] += 1
        
        return {"success": True, "market": m.question, "price": f"{fill:.2%}"}
    
    def close(self, market_id: str) -> Dict:
        """平仓"""
        if market_id not in self.positions:
            return {"error": "无持仓"}
        
        pos = self.positions[market_id]
        m = self.markets.get(market_id)
        
        sell = m.yes - random.uniform(0, 0.003) if m else pos["current"]
        proceeds = pos["size"] * sell
        pnl = proceeds - pos["size"] * pos["entry"]
        
        self.capital += proceeds
        self.stats["pnl"] += pnl
        if pnl > 0:
            self.stats["wins"] += 1
        
        del self.positions[market_id]
        
        return {"success": True, "pnl": f"${pnl:+.2f}"}
    
    def run_sim(self, steps: int = 100, auto: bool = False) -> Dict:
        """运行模拟"""
        for _ in range(steps):
            self.update_prices()
            if auto:
                self.scan()
                if self.opps:
                    opp = self.opps[0]
                    mid = opp.get("m1")
                    if mid and mid not in self.positions:
                        self.trade(mid, self.capital * 0.1)
            
            for pid in list(self.positions.keys()):
                if random.random() < 0.03:
                    self.close(pid)
        
        # 平仓所有
        for pid in list(self.positions.keys()):
            self.close(pid)
        
        pnl = self.capital - self.cfg.initial_capital
        return {
            "initial": f"${self.cfg.initial_capital:,.0f}",
            "final": f"${self.capital:,.0f}",
            "pnl": f"${pnl:+,.0f}",
            "return": f"{pnl/self.cfg.initial_capital*100:+.1f}%",
            "trades": self.stats["trades"],
            "win_rate": f"{self.stats['wins']/max(1,self.stats['trades'])*100:.0f}%"
        }
    
    def status(self) -> Dict:
        return {
            "capital": f"${self.capital:,.0f}",
            "positions": len(self.positions),
            "trades": self.stats["trades"],
            "pnl": f"${self.stats['pnl']:+,.0f}",
            "win_rate": f"{self.stats['wins']/max(1,self.stats['trades'])*100:.0f}%"
        }
    
    def reset(self):
        self.capital = self.cfg.initial_capital
        self.positions.clear()
        self.trades.clear()
        self.stats = {"trades": 0, "wins": 0, "pnl": 0}

sim = Simulator()

# ==================== Gradio 界面 ====================

with gr.Blocks(title="Polymarket 套利模拟器", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧪 Polymarket 套利模拟器\n**完全模拟测试 - 无需真实私钥**")
    
    with gr.Tabs():
        with gr.TabItem("📊 控制面板"):
            status_out = gr.JSON(label="状态", value=sim.status())
            
            with gr.Row():
                refresh_btn = gr.Button("🔄 刷新")
                reset_btn = gr.Button("🔃 重置")
                scan_btn = gr.Button("🔍 扫描机会", variant="primary")
            
            gr.Markdown("### 套利机会")
            opps_df = gr.Dataframe(
                headers=["类型", "市场1", "市场2", "利润", "操作"],
                value=[]
            )
            
            gr.Markdown("### 持仓")
            pos_df = gr.Dataframe(
                headers=["市场", "平台", "数量", "入场价", "当前价", "盈亏"],
                value=[]
            )
        
        with gr.TabItem("🧪 模拟测试"):
            with gr.Row():
                steps = gr.Slider(10, 500, 100, step=10, label="步数")
                auto = gr.Checkbox(False, label="自动交易")
            
            run_btn = gr.Button("▶️ 运行", variant="primary", size="lg")
            result_out = gr.JSON(label="结果")
        
        with gr.TabItem("💱 手动交易"):
            opp_dd = gr.Dropdown(label="选择机会", choices=[])
            size_in = gr.Number(100, label="金额 ($)")
            trade_btn = gr.Button("📈 买入", variant="primary")
            trade_out = gr.JSON(label="结果")
            
            pos_dd = gr.Dropdown(label="选择持仓", choices=[])
            close_btn = gr.Button("📉 平仓")
            close_out = gr.JSON(label="结果")
        
        with gr.TabItem("⚙️ 配置"):
            capital_in = gr.Number(1000, label="初始资金")
            max_pos_in = gr.Number(100, label="最大仓位")
            min_profit_in = gr.Slider(0.5, 5, 2, label="最小利润%")
            
            cfg_btn = gr.Button("💾 保存")
            cfg_out = gr.JSON(label="状态")
    
    # 事件
    def do_refresh():
        return sim.status()
    
    def do_reset():
        sim.reset()
        return sim.status()
    
    def do_scan():
        opps = sim.scan()
        df = [[o["type"], o["m1"], o.get("m2", "-"), o["profit"], o["action"][:20]] for o in opps]
        choices = [f"{o['m1']}: {o['profit']}" for o in opps]
        pos_choices = [f"{p}: ${sim.positions[p]['size']:.0f}" for p in sim.positions]
        return df, gr.Dropdown(choices=choices), gr.Dropdown(choices=pos_choices)
    
    def do_run(s, a):
        return sim.run_sim(int(s), a)
    
    def do_trade(opp_str, size):
        if not opp_str:
            return {"error": "请选择机会"}
        mid = opp_str.split(":")[0]
        return sim.trade(mid, size)
    
    def do_close(pos_str):
        if not pos_str:
            return {"error": "请选择持仓"}
        mid = pos_str.split(":")[0]
        return sim.close(mid)
    
    def do_cfg(capital, max_pos, min_profit):
        sim.cfg.initial_capital = capital
        sim.cfg.max_position = max_pos
        sim.cfg.min_profit = min_profit / 100
        sim.capital = capital
        return {"status": "已应用"}
    
    def get_positions():
        return [[
            sim.positions[p]["market"],
            sim.positions[p]["platform"],
            f"${sim.positions[p]['size']:.0f}",
            f"{sim.positions[p]['entry']:.1%}",
            f"{sim.positions[p]['current']:.1%}",
            f"${sim.positions[p]['pnl']:+.0f}"
        ] for p in sim.positions]
    
    refresh_btn.click(do_refresh, outputs=status_out)
    reset_btn.click(do_reset, outputs=status_out)
    scan_btn.click(do_scan, outputs=[opps_df, opp_dd, pos_dd])
    run_btn.click(do_run, inputs=[steps, auto], outputs=result_out)
    trade_btn.click(do_trade, inputs=[opp_dd, size_in], outputs=trade_out)
    close_btn.click(do_close, inputs=pos_dd, outputs=close_out)
    cfg_btn.click(do_cfg, inputs=[capital_in, max_pos_in, min_profit_in], outputs=cfg_out)

# FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {"status": "ok", "capital": sim.capital}

@app.get("/api/scan")
def api_scan():
    return sim.scan()

app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

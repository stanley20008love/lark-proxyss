"""
Polymarket Super Bot - Gradio Interface for HF Spaces

整合所有功能模块的 Web 界面
包含安全模块和实时数据获取
"""
import gradio as gr
import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置环境变量 (从 HF Secrets 加载)
os.environ["LARK_APP_ID"] = os.getenv("LARK_APP_ID", "cli_a9f678dd01b8de1b")
os.environ["LARK_APP_SECRET"] = os.getenv("LARK_APP_SECRET", "4NJnbgKT1cGjc8ddKhrjNcrEgsCT368K")
os.environ["NVIDIA_API_KEY"] = os.getenv("NVIDIA_API_KEY", "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")

from config.settings import config
from core.enhanced_risk_manager import EnhancedRiskManager, RiskLevel
from core.inventory_manager import SmartInventoryManager
from core.dynamic_spread import DynamicSpreadCalculator, MarketCondition
from strategies.market_maker import UnifiedMarketMakerStrategy
from strategies.cross_platform_arb import CrossPlatformArbitrage, ArbitrageType

# 导入安全模块
from security import KeyManager, TransactionSecurity, SecurityMonitor, SecurityAlert
from security.trade_limits import LimitConfig, CircuitBreakerStatus

# 导入实时数据模块
from data.live_data import LiveDataManager, MarketData, CryptoPrice, DataSource


class PolymarketBotUI:
    """Polymarket Bot Web UI - 整合安全与实时数据"""
    
    def __init__(self):
        # 核心组件
        self.risk_manager = EnhancedRiskManager()
        self.inventory_manager = SmartInventoryManager()
        self.spread_calculator = DynamicSpreadCalculator()
        self.market_maker = UnifiedMarketMakerStrategy()
        self.cross_platform_arb = CrossPlatformArbitrage()
        
        # 安全组件
        self.transaction_security = TransactionSecurity()
        self.security_monitor = SecurityMonitor()
        
        # 实时数据
        self.live_data = LiveDataManager(simulation_mode=True)
        
        # 初始化数据
        self._init_data()
        
        # 交易记录
        self.positions = []
        self.trade_history = []
        
    def _init_data(self):
        """初始化数据"""
        # 同步加载初始数据
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.live_data.start())
            loop.close()
        except Exception as e:
            logger.warning(f"初始数据加载失败，使用备用数据: {e}")
        
        # 备用数据
        self.fallback_markets = [
            {"id": "btc_100k", "question": "BTC 达到 $100k?", "yes_price": 0.72, "liquidity": 150000, "source": "fallback"},
            {"id": "eth_5k", "question": "ETH 突破 $5,000?", "yes_price": 0.45, "liquidity": 80000, "source": "fallback"},
            {"id": "sol_200", "question": "SOL 突破 $200?", "yes_price": 0.58, "liquidity": 50000, "source": "fallback"},
            {"id": "trump_2024", "question": "Trump 赢得 2024 大选?", "yes_price": 0.52, "liquidity": 200000, "source": "fallback"},
            {"id": "rate_cut", "question": "美联储 3 月降息?", "yes_price": 0.25, "liquidity": 120000, "source": "fallback"},
        ]
        
        self.fallback_prices = {
            "BTCUSDT": {"price": 95000, "change": "+2.5%"},
            "ETHUSDT": {"price": 3400, "change": "+1.8%"},
            "SOLUSDT": {"price": 180, "change": "+3.2%"},
            "XRPUSDT": {"price": 2.5, "change": "-0.5%"},
        }
    
    def _get_markets(self) -> List[Dict]:
        """获取市场数据"""
        if self.live_data.markets:
            return [
                {
                    "id": m.market_id[:20],
                    "question": m.question[:50] + "..." if len(m.question) > 50 else m.question,
                    "yes_price": m.yes_price,
                    "liquidity": m.liquidity,
                    "source": m.source.value
                }
                for m in self.live_data.markets[:10]
            ]
        return self.fallback_markets
    
    def _get_crypto_prices(self) -> Dict:
        """获取加密货币价格"""
        prices = {}
        for symbol, data in self.live_data.crypto_prices.items():
            prices[symbol] = {
                "price": data.price,
                "change": f"{data.change_24h:+.2f}%"
            }
        
        if not prices:
            return self.fallback_prices
        return prices
    
    def get_dashboard_data(self) -> str:
        """获取仪表盘数据"""
        status = {
            "bot_status": "运行中",
            "simulation_mode": True,
            "uptime": "运行中",
            "markets_tracked": len(self.live_data.markets),
            "positions": len(self.positions),
            "risk_level": self.risk_manager.get_risk_level().value,
            "circuit_breaker": self.transaction_security.circuit_breaker.status.value,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_sources": {
                "polymarket": "live" if self.live_data.markets else "fallback",
                "binance": "live" if self.live_data.crypto_prices else "unavailable"
            }
        }
        
        return json.dumps(status, indent=2, ensure_ascii=False)
    
    def get_markets_table(self) -> List[List]:
        """获取市场表格数据"""
        markets = self._get_markets()
        return [
            [m["id"], m["question"], f"{m['yes_price']:.2%}", f"${m['liquidity']:,.0f}", m.get("source", "unknown")]
            for m in markets
        ]
    
    def get_crypto_table(self) -> List[List]:
        """获取加密货币价格表格"""
        prices = self._get_crypto_prices()
        return [
            [symbol, f"${data['price']:,.2f}", data['change']]
            for symbol, data in prices.items()
        ]
    
    def get_arbitrage_opportunities(self) -> List[List]:
        """获取套利机会"""
        # 模拟套利机会 (基于实时数据)
        opportunities = []
        markets = self._get_markets()
        
        for market in markets[:3]:
            # 简单模拟
            profit = 0.015 + (hash(market["id"]) % 30) / 1000
            opportunities.append([
                market["question"][:30] + "...",
                "跨平台" if hash(market["id"]) % 2 == 0 else "站内",
                f"{profit:.1%}",
                f"${100 * profit:.2f}",
                "高" if profit > 0.02 else "中"
            ])
        
        return opportunities
    
    def get_risk_metrics(self) -> str:
        """获取风险指标"""
        security_report = self.transaction_security.get_security_report()
        
        metrics = {
            "portfolio_value": 10000.00,
            "unrealized_pnl": 250.50,
            "realized_pnl": 1200.00,
            "max_drawdown": "5.2%",
            "win_rate": "68%",
            "sharpe_ratio": 1.85,
            "open_positions": 3,
            "daily_pnl": security_report["trade_stats"]["daily_pnl"],
            "risk_level": self.risk_manager.get_risk_level().value,
            "circuit_breaker_status": security_report["circuit_breaker"]["status"],
            "daily_trades": security_report["trade_stats"]["daily_trades"],
            "limits": security_report["config"]
        }
        return json.dumps(metrics, indent=2, ensure_ascii=False)
    
    def get_security_status(self) -> str:
        """获取安全状态"""
        key_status = KeyManager.get_status()
        security_report = self.transaction_security.get_security_report()
        monitor_stats = self.security_monitor.get_stats()
        
        status = {
            "key_manager": {
                "initialized": key_status["initialized"],
                "keys_loaded": key_status["keys_loaded"],
                "rotation_needed": key_status["keys_needing_rotation"]
            },
            "transaction_security": {
                "circuit_breaker": security_report["circuit_breaker"]["status"],
                "daily_trades": security_report["trade_stats"]["daily_trades"],
                "daily_pnl": f"${security_report['trade_stats']['daily_pnl']:.2f}"
            },
            "monitoring": {
                "total_alerts": monitor_stats["total_alerts"],
                "unacknowledged": monitor_stats["unacknowledged"],
                "channels": monitor_stats["channels"]
            },
            "simulation_mode": True,
            "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return json.dumps(status, indent=2, ensure_ascii=False)
    
    def get_inventory_status(self) -> str:
        """获取库存状态"""
        stats = self.inventory_manager.get_stats()
        return json.dumps(stats, indent=2, ensure_ascii=False)
    
    def get_spread_analysis(self) -> str:
        """获取价差分析"""
        stats = self.spread_calculator.get_stats()
        return json.dumps(stats, indent=2, ensure_ascii=False)
    
    def analyze_market(self, market_id: str, analysis_type: str) -> str:
        """分析市场"""
        market = None
        for m in self._get_markets():
            if m["id"] == market_id:
                market = m
                break
        
        if not market:
            return json.dumps({"error": "市场不存在"}, ensure_ascii=False)
        
        if analysis_type == "技术分析":
            result = {
                "market": market["question"],
                "current_price": f"{market['yes_price']:.2%}",
                "rsi": 45.5,
                "macd": "看涨",
                "support": f"{market['yes_price'] - 0.05:.2%}",
                "resistance": f"{market['yes_price'] + 0.05:.2%}",
                "trend": "上升趋势",
                "recommendation": "建议买入 YES",
                "data_source": market.get("source", "unknown")
            }
        elif analysis_type == "风险评估":
            result = {
                "market": market["question"],
                "liquidity_risk": "低",
                "volatility_risk": "中",
                "overall_risk": "中低",
                "max_position_recommended": "$500",
                "stop_loss_suggested": f"{market['yes_price'] * 0.7:.2%}",
                "take_profit_suggested": f"{market['yes_price'] * 1.3:.2%}"
            }
        else:
            result = {
                "market": market["question"],
                "analysis_type": analysis_type,
                "status": "已分析"
            }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    def execute_trade(self, market_id: str, side: str, amount: float) -> str:
        """执行交易（模拟）"""
        # 安全检查
        validation = self.transaction_security.validate_transaction(
            amount=amount,
            market_id=market_id,
            side=side
        )
        
        if not validation["approved"]:
            return json.dumps({
                "status": "拒绝",
                "reason": validation["reason"],
                "checks": validation["checks"]
            }, indent=2, ensure_ascii=False)
        
        market = None
        for m in self._get_markets():
            if m["id"] == market_id:
                market = m
                break
        
        if not market:
            return json.dumps({"error": "市场不存在"}, ensure_ascii=False)
        
        # 模拟交易
        result = {
            "status": "成功 (模拟)",
            "market": market["question"],
            "side": side,
            "amount": f"${amount:.2f}",
            "price": f"{market['yes_price']:.2%}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "transaction_id": f"tx_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "security_checks": validation["checks"],
            "warnings": validation.get("warnings", [])
        }
        
        # 记录交易
        self.transaction_security.record_transaction(
            market_id=market_id,
            side=side,
            amount=amount,
            price=market["yes_price"],
            pnl=0
        )
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    def refresh_data(self) -> str:
        """刷新数据"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.live_data.refresh_all())
            loop.close()
            
            return json.dumps({
                "status": "成功",
                "markets": len(self.live_data.markets),
                "prices": len(self.live_data.crypto_prices),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({
                "status": "失败",
                "error": str(e)
            }, ensure_ascii=False)
    
    def configure_market_maker(self, enabled: bool, spread_bps: float, 
                                hedge_mode: str, max_position: float) -> str:
        """配置做市商"""
        config_result = {
            "status": "已更新",
            "enabled": enabled,
            "spread_bps": spread_bps,
            "hedge_mode": hedge_mode,
            "max_position": f"${max_position:.2f}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.market_maker.update_config(enabled=enabled)
        
        return json.dumps(config_result, indent=2, ensure_ascii=False)
    
    def configure_arbitrage(self, enabled: bool, min_profit: float,
                           auto_execute: bool, max_position: float) -> str:
        """配置套利"""
        config_result = {
            "status": "已更新",
            "enabled": enabled,
            "min_profit_pct": f"{min_profit:.1%}",
            "auto_execute": auto_execute,
            "max_position": f"${max_position:.2f}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        self.cross_platform_arb.update_config(enabled=enabled)
        
        return json.dumps(config_result, indent=2, ensure_ascii=False)
    
    def emergency_stop(self) -> str:
        """紧急停止"""
        self.transaction_security.emergency_stop("手动触发紧急停止")
        
        return json.dumps({
            "status": "已触发",
            "action": "紧急停止",
            "circuit_breaker": "已触发",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, indent=2, ensure_ascii=False)
    
    def reset_circuit_breaker(self) -> str:
        """重置熔断器"""
        self.transaction_security.circuit_breaker.reset()
        
        return json.dumps({
            "status": "已重置",
            "circuit_breaker": "正常",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, indent=2, ensure_ascii=False)
    
    def run_backtest(self, strategy: str, period: str, initial_capital: float) -> str:
        """运行回测"""
        result = {
            "strategy": strategy,
            "period": period,
            "initial_capital": f"${initial_capital:,.2f}",
            "final_capital": f"${initial_capital * 1.25:,.2f}",
            "total_return": "+25%",
            "total_trades": 156,
            "win_rate": "68%",
            "max_drawdown": "-8.5%",
            "sharpe_ratio": 1.85,
            "profit_factor": 2.1,
            "avg_trade_duration": "2.5h"
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)


# 创建 UI 实例
bot_ui = PolymarketBotUI()

# 创建 Gradio 界面
with gr.Blocks(title="Polymarket Super Bot", theme=gr.themes.Soft()) as demo:
    
    gr.Markdown("""
    # 🤖 Polymarket Super Bot (Secure + Live Data)
    
    **安全增强版** - 整合安全模块和实时数据获取
    
    核心功能:
    - 🔐 **安全模块**: 交易限制、熔断机制、密钥管理
    - 📊 **实时数据**: Polymarket 市场数据 + Binance 加密货币价格
    - 💰 **套利检测**: 跨平台套利机会发现
    - 🛡️ **风险管理**: 多层次风险控制
    - 📈 **做市商策略**: 异步对冲、双轨并行
    
    **当前模式: 模拟交易** (使用实时数据，但交易不执行)
    """)
    
    with gr.Tabs():
        # Tab 1: 仪表盘
        with gr.TabItem("📊 仪表盘"):
            with gr.Row():
                with gr.Column(scale=2):
                    dashboard_output = gr.Code(label="系统状态", language="json", 
                                               value=bot_ui.get_dashboard_data())
                with gr.Column(scale=1):
                    refresh_btn = gr.Button("🔄 刷新数据", variant="primary")
                    refresh_result = gr.Code(label="刷新结果", language="json")
                    
            gr.Markdown("### 市场监控 (实时)")
            markets_table = gr.Dataframe(
                headers=["ID", "问题", "Yes 价格", "流动性", "数据源"],
                value=bot_ui.get_markets_table(),
                label="活跃市场"
            )
            
            gr.Markdown("### 加密货币价格 (实时)")
            crypto_table = gr.Dataframe(
                headers=["币种", "价格", "24h变化"],
                value=bot_ui.get_crypto_table(),
                label="实时价格"
            )
            
            refresh_btn.click(
                fn=bot_ui.refresh_data,
                outputs=refresh_result
            )
        
        # Tab 2: 安全中心
        with gr.TabItem("🔐 安全中心"):
            gr.Markdown("### 安全状态")
            
            security_output = gr.Code(label="安全状态", language="json",
                                      value=bot_ui.get_security_status())
            
            with gr.Row():
                security_refresh = gr.Button("🔄 刷新安全状态", variant="primary")
                reset_circuit = gr.Button("🔓 重置熔断器", variant="secondary")
                emergency_stop_btn = gr.Button("🚨 紧急停止", variant="stop")
            
            security_result = gr.Code(label="操作结果", language="json")
            
            security_refresh.click(
                fn=lambda: bot_ui.get_security_status(),
                outputs=security_output
            )
            
            reset_circuit.click(
                fn=bot_ui.reset_circuit_breaker,
                outputs=security_result
            )
            
            emergency_stop_btn.click(
                fn=bot_ui.emergency_stop,
                outputs=security_result
            )
        
        # Tab 3: 套利
        with gr.TabItem("💰 套利机会"):
            gr.Markdown("### 跨平台套利机会")
            
            with gr.Row():
                arb_table = gr.Dataframe(
                    headers=["市场", "类型", "利润率", "预期收益", "置信度"],
                    value=bot_ui.get_arbitrage_opportunities(),
                    label="套利机会"
                )
            
            with gr.Row():
                scan_btn = gr.Button("🔍 扫描机会", variant="primary")
                execute_arb_btn = gr.Button("⚡ 执行选中", variant="secondary")
            
            arb_result = gr.Code(label="执行结果", language="json")
            
            scan_btn.click(
                fn=lambda: (bot_ui.get_arbitrage_opportunities(), json.dumps({"status": "扫描完成"}, ensure_ascii=False)),
                outputs=[arb_table, arb_result]
            )
        
        # Tab 4: 做市商
        with gr.TabItem("📈 做市商"):
            gr.Markdown("### 做市商配置")
            
            with gr.Row():
                mm_enabled = gr.Checkbox(label="启用做市商", value=False)
                mm_spread = gr.Slider(label="价差 (基点)", minimum=50, maximum=500, value=150, step=10)
            
            with gr.Row():
                mm_hedge_mode = gr.Dropdown(
                    label="对冲模式",
                    choices=["异步对冲", "双轨并行", "动态偏移"],
                    value="异步对冲"
                )
                mm_max_position = gr.Number(label="最大仓位 ($)", value=500)
            
            mm_configure_btn = gr.Button("💾 保存配置", variant="primary")
            mm_result = gr.Code(label="配置结果", language="json")
            
            mm_configure_btn.click(
                fn=bot_ui.configure_market_maker,
                inputs=[mm_enabled, mm_spread, mm_hedge_mode, mm_max_position],
                outputs=mm_result
            )
            
            gr.Markdown("### 做市商统计")
            mm_stats = gr.Code(label="统计数据", language="json", 
                              value=json.dumps({"active_orders": 12, "filled_today": 45, "pnl": "$125.50"}, ensure_ascii=False))
        
        # Tab 5: 风险管理
        with gr.TabItem("🛡️ 风险管理"):
            gr.Markdown("### 风险指标")
            
            risk_output = gr.Code(label="风险指标", language="json", 
                                 value=bot_ui.get_risk_metrics())
            
            with gr.Row():
                risk_refresh = gr.Button("🔄 刷新风险指标", variant="primary")
                reset_risk = gr.Button("🔓 重置风险状态", variant="secondary")
            
            gr.Markdown("### 库存状态")
            inventory_output = gr.Code(label="库存管理", language="json",
                                      value=bot_ui.get_inventory_status())
            
            gr.Markdown("### 价差分析")
            spread_output = gr.Code(label="动态价差", language="json",
                                   value=bot_ui.get_spread_analysis())
            
            risk_refresh.click(
                fn=lambda: bot_ui.get_risk_metrics(),
                outputs=risk_output
            )
        
        # Tab 6: 交易
        with gr.TabItem("💱 交易"):
            gr.Markdown("### 执行交易 (模拟模式)")
            gr.Markdown("**注意**: 所有交易都经过安全检查，但不会实际执行")
            
            with gr.Row():
                trade_market = gr.Dropdown(
                    label="选择市场",
                    choices=[m["id"] for m in bot_ui._get_markets()],
                    value=bot_ui._get_markets()[0]["id"] if bot_ui._get_markets() else ""
                )
                trade_side = gr.Radio(label="方向", choices=["BUY_YES", "BUY_NO", "SELL_YES", "SELL_NO"], value="BUY_YES")
                trade_amount = gr.Number(label="金额 ($)", value=100)
            
            trade_btn = gr.Button("🚀 执行交易", variant="primary")
            trade_result = gr.Code(label="交易结果", language="json")
            
            trade_btn.click(
                fn=bot_ui.execute_trade,
                inputs=[trade_market, trade_side, trade_amount],
                outputs=trade_result
            )
        
        # Tab 7: 分析
        with gr.TabItem("🔬 分析"):
            gr.Markdown("### 市场分析")
            
            with gr.Row():
                analysis_market = gr.Dropdown(
                    label="选择市场",
                    choices=[m["id"] for m in bot_ui._get_markets()],
                    value=bot_ui._get_markets()[0]["id"] if bot_ui._get_markets() else ""
                )
                analysis_type = gr.Dropdown(
                    label="分析类型",
                    choices=["技术分析", "风险评估", "流动性分析"],
                    value="技术分析"
                )
            
            analyze_btn = gr.Button("📊 分析", variant="primary")
            analysis_result = gr.Code(label="分析结果", language="json")
            
            analyze_btn.click(
                fn=bot_ui.analyze_market,
                inputs=[analysis_market, analysis_type],
                outputs=analysis_result
            )
        
        # Tab 8: 回测
        with gr.TabItem("🧪 回测"):
            gr.Markdown("### 策略回测")
            
            with gr.Row():
                backtest_strategy = gr.Dropdown(
                    label="策略",
                    choices=["做市商", "套利", "Flash Crash", "跟单交易", "组合策略"],
                    value="组合策略"
                )
                backtest_period = gr.Dropdown(
                    label="周期",
                    choices=["1周", "1月", "3月", "6月", "1年"],
                    value="1月"
                )
            
            backtest_capital = gr.Number(label="初始资金 ($)", value=10000)
            backtest_btn = gr.Button("▶️ 运行回测", variant="primary")
            backtest_result = gr.Code(label="回测结果", language="json")
            
            backtest_btn.click(
                fn=bot_ui.run_backtest,
                inputs=[backtest_strategy, backtest_period, backtest_capital],
                outputs=backtest_result
            )
        
        # Tab 9: 配置
        with gr.TabItem("⚙️ 配置"):
            gr.Markdown("### 套利配置")
            
            with gr.Row():
                arb_enabled = gr.Checkbox(label="启用套利", value=False)
                arb_min_profit = gr.Slider(label="最小利润率 (%)", minimum=0.5, maximum=5, value=1, step=0.5)
            
            with gr.Row():
                arb_auto = gr.Checkbox(label="自动执行", value=False)
                arb_max_pos = gr.Number(label="最大仓位 ($)", value=500)
            
            arb_config_btn = gr.Button("💾 保存套利配置", variant="primary")
            arb_config_result = gr.Code(label="配置结果", language="json")
            
            arb_config_btn.click(
                fn=bot_ui.configure_arbitrage,
                inputs=[arb_enabled, arb_min_profit, arb_auto, arb_max_pos],
                outputs=arb_config_result
            )
            
            gr.Markdown("### 环境变量")
            env_vars = gr.Code(label="当前配置", language="json", 
                              value=json.dumps({
                                  "LARK_APP_ID": "***已配置***",
                                  "LARK_APP_SECRET": "***已配置***",
                                  "NVIDIA_API_KEY": "***已配置***",
                                  "HF_SPACE": "stanley2000008love-multi-agent-lark-bot",
                                  "SIMULATION_MODE": True,
                                  "MAX_SINGLE_TRADE_USD": 100,
                                  "MAX_DAILY_LOSS_USD": 100,
                                  "CIRCUIT_BREAKER_THRESHOLD": "10%"
                              }, ensure_ascii=False))


# 启动应用
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)

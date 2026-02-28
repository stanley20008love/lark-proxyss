"""
Polymarket Super Bot - 配置管理 (Enhanced)

整合了所有模块的配置
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


@dataclass
class TradingConfig:
    """交易配置"""
    MAX_POSITION_SIZE: float = 100.0
    MAX_DAILY_LOSS: float = 50.0
    STOP_LOSS_PCT: float = 0.30
    TAKE_PROFIT_PCT: float = 0.20
    FLASH_CRASH_THRESHOLD: float = 0.25
    FLASH_CRASH_WINDOW: int = 10
    COPY_TRADE_RATIO: float = 0.5
    MIN_COPY_SIZE: float = 1.0
    MAX_COPY_SIZE: float = 50.0
    SIMULATION_MODE: bool = True
    AUTO_TRADE: bool = False
    SUPPORTED_COINS: List[str] = field(default_factory=lambda: ["BTC", "ETH", "SOL", "XRP"])


@dataclass
class AnalysisConfig:
    """技术分析配置"""
    RSI_PERIOD: int = 14
    RSI_OVERSOLD: float = 30.0
    RSI_OVERBOUGHT: float = 70.0
    MACD_FAST: int = 12
    MACD_SLOW: int = 26
    MACD_SIGNAL: int = 9


@dataclass
class LarkConfig:
    """飞书配置"""
    APP_ID: str = field(default_factory=lambda: os.getenv("LARK_APP_ID", ""))
    APP_SECRET: str = field(default_factory=lambda: os.getenv("LARK_APP_SECRET", ""))
    API_URL: str = "https://open.larksuite.com/open-apis"


@dataclass
class BacktestConfig:
    """回测配置"""
    INITIAL_CAPITAL: float = 1000.0
    COMMISSION: float = 0.001
    SLIPPAGE: float = 0.0005


@dataclass
class MarketMakerConfig:
    """做市商配置"""
    # 基础设置
    ENABLED: bool = False
    TOLERANCE: float = 0.05           # 对冲偏差容忍度 5%
    MIN_HEDGE_SIZE: float = 10.0      # 最小对冲数量
    MAX_HEDGE_SIZE: float = 500.0     # 最大对冲数量
    
    # 价差设置
    BUY_SPREAD_BPS: float = 150.0     # Buy 价差 1.5%
    SELL_SPREAD_BPS: float = 150.0    # Sell 价差 1.5%
    MIN_SPREAD: float = 0.005         # 最小价差 0.5%
    MAX_SPREAD: float = 0.10          # 最大价差 10%
    
    # 对冲设置
    HEDGE_SLIPPAGE_BPS: float = 250.0
    ASYNC_HEDGING: bool = True        # 异步对冲
    DUAL_TRACK_MODE: bool = True      # 双轨并行
    DYNAMIC_OFFSET_MODE: bool = True  # 动态偏移
    
    # 积分规则 (Predict.fun)
    LIQUIDITY_MIN_SHARES: int = 100
    LIQUIDITY_MAX_SPREAD_CENTS: int = 6


@dataclass
class ArbitrageConfig:
    """套利配置"""
    # 跨平台套利
    CROSS_PLATFORM_ENABLED: bool = False
    MIN_PROFIT_PCT: float = 0.01          # 最小利润率 1%
    MIN_SIMILARITY: float = 0.78          # 最小相似度
    AUTO_EXECUTE: bool = False
    REQUIRE_CONFIRM: bool = True
    TRANSFER_COST: float = 0.002
    SLIPPAGE_BPS: float = 250.0
    MAX_POSITION_USD: float = 500.0
    FEE_BPS: float = 100.0
    
    # 站内套利
    INTRA_PLATFORM_ENABLED: bool = True
    
    # 扫描设置
    SCAN_INTERVAL_MS: int = 10000
    MAX_MARKETS: int = 80


@dataclass
class RiskManagementConfig:
    """风险管理配置"""
    # 仓位限制
    MAX_POSITION_SIZE: float = 100.0
    MAX_DAILY_LOSS: float = 50.0
    MAX_DRAWDOWN: float = 0.20
    
    # 止损止盈
    STOP_LOSS_PCT: float = 0.30
    TAKE_PROFIT_PCT: float = 0.20
    TRAILING_STOP_PCT: float = 0.10
    
    # 熔断
    CIRCUIT_BREAKER_THRESHOLD: float = 0.10
    CIRCUIT_BREAKER_COOLDOWN: int = 3600
    
    # 波动暂停
    VOLATILITY_THRESHOLD: float = 0.02
    VOLATILITY_LOOKBACK: int = 10
    VOLATILITY_PAUSE_DURATION: int = 300
    
    # 冷却时间
    COOLDOWN_AFTER_CANCEL: int = 4
    COOLDOWN_AFTER_TRADE: int = 10
    
    # 滑点控制
    MAX_SLIPPAGE_BPS: float = 250.0


@dataclass
class SecurityConfig:
    """安全配置"""
    # 模拟模式 (始终开启以确保安全)
    SIMULATION_MODE: bool = True
    
    # 单笔交易限制
    MAX_SINGLE_TRADE_USD: float = 100.0
    MAX_SINGLE_TRADE_PCT: float = 0.10
    
    # 每日限制
    MAX_DAILY_TRADES: int = 100
    MAX_DAILY_VOLUME_USD: float = 5000.0
    MAX_DAILY_VOLUME_PCT: float = 0.50
    
    # 亏损限制
    MAX_DAILY_LOSS_USD: float = 100.0
    MAX_DAILY_LOSS_PCT: float = 0.05
    
    # 熔断设置
    CIRCUIT_BREAKER_THRESHOLD: float = 0.10
    CIRCUIT_BREAKER_COOLDOWN: int = 3600
    
    # 异常检测
    MAX_TRADES_PER_MINUTE: int = 10
    MAX_UNUSUAL_SIZE_MULTIPLIER: float = 5.0
    
    # 告警设置
    ALERT_LARGE_TRANSACTION_USD: float = 100.0
    ALERT_LOSS_WARNING_PCT: float = 0.03
    ALERT_LOSS_CRITICAL_PCT: float = 0.05
    
    # 密钥轮换
    KEY_ROTATION_DAYS: int = 90


@dataclass
class InventoryConfig:
    """库存管理配置"""
    MAX_POSITION: float = 100.0
    MAX_NET_EXPOSURE: float = 50.0
    HEDGE_THRESHOLD: float = 0.7
    HEDGE_RATIO: float = 0.5
    RISK_MULTIPLIER: float = 1.5
    ENABLE_AUTO_HEDGE: bool = True
    VOLATILITY_THRESHOLD: float = 0.02


@dataclass
class DynamicSpreadConfig:
    """动态价差配置"""
    BASE_SPREAD: float = 0.02
    MIN_SPREAD: float = 0.005
    MAX_SPREAD: float = 0.10
    VOLATILITY_WEIGHT: float = 0.30
    LIQUIDITY_WEIGHT: float = 0.25
    VOLUME_WEIGHT: float = 0.20
    PRESSURE_WEIGHT: float = 0.15
    ADJUSTMENT_SPEED: float = 0.5
    CONFIDENCE_THRESHOLD: float = 0.6


@dataclass
class WebSocketConfig:
    """WebSocket 配置"""
    POLYMARKET_WS_URL: str = "wss://clob.polymarket.com/ws"
    PREDICT_WS_URL: str = "wss://ws.predict.fun/ws"
    RECONNECT_INTERVAL: int = 5
    HEARTBEAT_INTERVAL: int = 30


@dataclass
class Config:
    """主配置类"""
    trading: TradingConfig = field(default_factory=TradingConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    lark: LarkConfig = field(default_factory=LarkConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    market_maker: MarketMakerConfig = field(default_factory=MarketMakerConfig)
    arbitrage: ArbitrageConfig = field(default_factory=ArbitrageConfig)
    risk: RiskManagementConfig = field(default_factory=RiskManagementConfig)
    inventory: InventoryConfig = field(default_factory=InventoryConfig)
    dynamic_spread: DynamicSpreadConfig = field(default_factory=DynamicSpreadConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # Polymarket API
    CLOB_HTTP_URL: str = "https://clob.polymarket.com"
    CLOB_WS_URL: str = "wss://clob.polymarket.com"
    
    # Predict.fun API
    PREDICT_HTTP_URL: str = "https://api.predict.fun"
    PREDICT_API_KEY: str = field(default_factory=lambda: os.getenv("PREDICT_API_KEY", ""))
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    
    # NVIDIA API (AI 功能)
    NVIDIA_API_KEY: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", ""))


# 全局配置实例
config = Config()

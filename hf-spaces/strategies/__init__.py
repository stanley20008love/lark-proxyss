"""
策略模块
"""
from strategies.flash_crash import FlashCrashStrategy
from strategies.copy_trading import CopyTradingBot
from strategies.market_maker import (
    UnifiedMarketMakerStrategy,
    UnifiedState,
    UnifiedAction,
    ActionType,
    Priority
)
from strategies.cross_platform_arb import (
    CrossPlatformArbitrage,
    ArbitrageType,
    ArbitrageOpportunity,
    Platform as ArbPlatform
)

__all__ = [
    "FlashCrashStrategy",
    "CopyTradingBot",
    "UnifiedMarketMakerStrategy",
    "UnifiedState",
    "UnifiedAction",
    "ActionType",
    "Priority",
    "CrossPlatformArbitrage",
    "ArbitrageType",
    "ArbitrageOpportunity",
    "ArbPlatform",
]

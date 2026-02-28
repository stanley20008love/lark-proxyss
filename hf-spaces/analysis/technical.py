"""
技术分析模块
RSI, MACD, VWAP, 布林带
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from config.settings import config


@dataclass
class Signal:
    """交易信号"""
    direction: str  # LONG, SHORT, NEUTRAL
    strength: float  # 0.0 - 1.0
    indicator: str
    value: float
    timestamp: float


class TechnicalAnalysis:
    """技术分析引擎"""
    
    def __init__(self):
        self.rsi_period = config.analysis.RSI_PERIOD
        self.rsi_oversold = config.analysis.RSI_OVERSOLD
        self.rsi_overbought = config.analysis.RSI_OVERBOUGHT
        self.macd_fast = config.analysis.MACD_FAST
        self.macd_slow = config.analysis.MACD_SLOW
        self.macd_signal = config.analysis.MACD_SIGNAL
    
    # ==================== RSI ====================
    
    def calculate_rsi(self, prices: List[float]) -> Tuple[float, np.ndarray]:
        """计算 RSI"""
        prices_arr = np.array(prices)
        deltas = np.diff(prices_arr)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.convolve(gains, np.ones(self.rsi_period)/self.rsi_period, mode='valid')
        avg_loss = np.convolve(losses, np.ones(self.rsi_period)/self.rsi_period, mode='valid')
        
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0)
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi[-1]) if len(rsi) > 0 else 50.0, rsi
    
    def get_rsi_signal(self, prices: List[float]) -> Signal:
        """获取 RSI 信号"""
        rsi_value, _ = self.calculate_rsi(prices)
        
        if rsi_value < self.rsi_oversold:
            direction = "LONG"
            strength = (self.rsi_oversold - rsi_value) / self.rsi_oversold
        elif rsi_value > self.rsi_overbought:
            direction = "SHORT"
            strength = (rsi_value - self.rsi_overbought) / (100 - self.rsi_overbought)
        else:
            direction = "NEUTRAL"
            strength = 0.0
        
        return Signal(direction, min(strength, 1.0), "RSI", rsi_value, datetime.now().timestamp())
    
    # ==================== MACD ====================
    
    def calculate_macd(self, prices: List[float]) -> Tuple[float, float, float]:
        """计算 MACD"""
        prices_series = pd.Series(prices)
        
        ema_fast = prices_series.ewm(span=self.macd_fast, adjust=False).mean()
        ema_slow = prices_series.ewm(span=self.macd_slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=self.macd_signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return float(macd_line.iloc[-1]), float(signal_line.iloc[-1]), float(histogram.iloc[-1])
    
    def get_macd_signal(self, prices: List[float]) -> Signal:
        """获取 MACD 信号"""
        macd, signal, hist = self.calculate_macd(prices)
        
        if hist > 0:
            direction = "LONG"
            strength = min(abs(hist) * 100, 1.0)
        elif hist < 0:
            direction = "SHORT"
            strength = min(abs(hist) * 100, 1.0)
        else:
            direction = "NEUTRAL"
            strength = 0.0
        
        return Signal(direction, strength, "MACD", hist, datetime.now().timestamp())
    
    # ==================== 综合信号 ====================
    
    def get_combined_signal(self, prices: List[float]) -> Dict:
        """获取综合信号"""
        signals = []
        
        if len(prices) >= self.rsi_period + 1:
            signals.append(self.get_rsi_signal(prices))
        
        if len(prices) >= self.macd_slow + 1:
            signals.append(self.get_macd_signal(prices))
        
        # 加权投票
        long_score = sum(s.strength for s in signals if s.direction == "LONG")
        short_score = sum(s.strength for s in signals if s.direction == "SHORT")
        total = long_score + short_score
        
        if total == 0:
            final_direction = "NEUTRAL"
            final_strength = 0.0
        elif long_score > short_score:
            final_direction = "LONG"
            final_strength = long_score / total
        else:
            final_direction = "SHORT"
            final_strength = short_score / total
        
        return {
            "direction": final_direction,
            "strength": final_strength,
            "signals": [{"indicator": s.indicator, "direction": s.direction, "strength": s.strength} for s in signals]
        }

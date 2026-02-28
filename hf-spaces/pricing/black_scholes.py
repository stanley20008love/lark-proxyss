"""
Polymarket 二元期权定价模型

基于 Black-Scholes 模型为 Polymarket 涨跌预测市场定价
- 二元看涨期权（Yes）定价
- 隐含波动率估算
- 公允价格计算
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
import numpy as np
from scipy import stats
from scipy.optimize import brentq


class OptionType(Enum):
    CALL = "call"  # Yes (Up)
    PUT = "put"    # No (Down)


@dataclass
class PricingResult:
    """定价结果"""
    theoretical_price: float      # 理论价格
    market_price: float           # 市场价格
    mispricing: float             # 定价偏差 (正=市场低估, 负=市场高估)
    mispricing_pct: float         # 定价偏差百分比
    edge: float                   # 优势 (扣除费用后)
    delta: float                  # Delta 希腊值
    gamma: float                  # Gamma
    vega: float                   # Vega
    theta: float                  # Theta
    implied_vol: float            # 隐含波动率
    confidence: float             # 置信度
    recommendation: str           # 推荐操作


class BlackScholesBinary:
    """
    Black-Scholes 二元期权定价模型

    Polymarket 的涨跌市场本质上是二元期权：
    - 如果事件发生，支付 $1
    - 如果事件不发生，支付 $0

    二元看涨期权定价公式：
    C_binary = e^(-rT) * N(d2)

    其中：
    d2 = (ln(S/K) + (r - σ²/2)T) / (σ√T)
    """

    def __init__(self, risk_free_rate: float = 0.05):
        """
        初始化定价模型

        Args:
            risk_free_rate: 无风险利率 (默认 5%)
        """
        self.r = risk_free_rate

    @staticmethod
    def norm_cdf(x: float) -> float:
        """标准正态累积分布函数"""
        return stats.norm.cdf(x)

    @staticmethod
    def norm_pdf(x: float) -> float:
        """标准正态概率密度函数"""
        return stats.norm.pdf(x)

    def d1(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        计算 d1

        Args:
            S: 标的资产当前价格
            K: 行权价
            T: 到期时间 (年)
            sigma: 波动率
        """
        if T <= 0 or sigma <= 0:
            return 0
        return (math.log(S / K) + (self.r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    def d2(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        计算 d2

        d2 = d1 - σ√T
        """
        if T <= 0 or sigma <= 0:
            return 0
        return self.d1(S, K, T, sigma) - sigma * math.sqrt(T)

    def binary_call_price(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        二元看涨期权定价 (Yes/Up)

        C_binary = e^(-rT) * N(d2)

        Args:
            S: 标的资产当前价格
            K: 行权价 (目标价格)
            T: 到期时间 (年)
            sigma: 波动率

        Returns:
            二元看涨期权价格 (0-1)
        """
        if T <= 0:
            # 已到期，看是否在价内
            return 1.0 if S >= K else 0.0

        if sigma <= 0:
            sigma = 0.01  # 最小波动率

        d2 = self.d2(S, K, T, sigma)
        price = math.exp(-self.r * T) * self.norm_cdf(d2)

        return max(0.001, min(0.999, price))  # 限制在 (0.001, 0.999)

    def binary_put_price(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        二元看跌期权定价 (No/Down)

        P_binary = e^(-rT) * N(-d2)
        """
        if T <= 0:
            return 1.0 if S < K else 0.0

        d2 = self.d2(S, K, T, sigma)
        put_price = math.exp(-self.r * T) * self.norm_cdf(-d2)

        return max(0.001, min(0.999, put_price))

    def delta(self, S: float, K: float, T: float, sigma: float, option_type: OptionType = OptionType.CALL) -> float:
        """
        计算 Delta (价格对标的资产的敏感度)
        """
        if T <= 0 or sigma <= 0:
            return 0

        d2 = self.d2(S, K, T, sigma)
        delta = math.exp(-self.r * T) * self.norm_pdf(d2) / (S * sigma * math.sqrt(T))

        if option_type == OptionType.PUT:
            delta = -delta

        return delta

    def vega(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        计算 Vega (价格对波动率的敏感度)
        """
        if T <= 0 or sigma <= 0:
            return 0

        d2 = self.d2(S, K, T, sigma)
        vega = -math.exp(-self.r * T) * self.norm_pdf(d2) * d2 / sigma

        return vega

    def theta(self, S: float, K: float, T: float, sigma: float) -> float:
        """
        计算 Theta (价格对时间的敏感度)
        """
        if T <= 0 or sigma <= 0:
            return 0

        d2 = self.d2(S, K, T, sigma)
        theta = self.r * math.exp(-self.r * T) * self.norm_cdf(d2)

        return theta

    def implied_volatility(self, market_price: float, S: float, K: float, T: float,
                          option_type: OptionType = OptionType.CALL,
                          max_iter: int = 100) -> float:
        """
        从市场价格反推隐含波动率

        使用 Brent 方法求解
        """
        if T <= 0:
            return 0.0

        def price_diff(sigma):
            if option_type == OptionType.CALL:
                model_price = self.binary_call_price(S, K, T, sigma)
            else:
                model_price = self.binary_put_price(S, K, T, sigma)
            return model_price - market_price

        sigma_low = 0.001
        sigma_high = 5.0

        try:
            p_low = price_diff(sigma_low)
            p_high = price_diff(sigma_high)

            if p_low * p_high > 0:
                return 0.5 if market_price > 0.5 else 0.8

            iv = brentq(price_diff, sigma_low, sigma_high, maxiter=max_iter)
            return iv
        except:
            return 0.5

    def price_binary_option(self, S: float, K: float, T: float, sigma: float,
                           market_price: float, option_type: OptionType = OptionType.CALL,
                           fee_rate: float = 0.02) -> PricingResult:
        """
        完整的二元期权定价分析
        """
        # 计算理论价格
        if option_type == OptionType.CALL:
            theoretical = self.binary_call_price(S, K, T, sigma)
        else:
            theoretical = self.binary_put_price(S, K, T, sigma)

        # 计算定价偏差
        mispricing = theoretical - market_price
        mispricing_pct = mispricing / market_price if market_price > 0 else 0

        # 计算优势 (扣除费用)
        edge = mispricing - fee_rate

        # 计算希腊值
        delta = self.delta(S, K, T, sigma, option_type)
        gamma = self.gamma(S, K, T, sigma)
        vega = self.vega(S, K, T, sigma)
        theta = self.theta(S, K, T, sigma)

        # 反推隐含波动率
        implied_vol = self.implied_volatility(market_price, S, K, T, option_type)

        # 计算置信度
        confidence = self._calculate_confidence(mispricing, T, sigma)

        # 生成推荐
        recommendation = self._generate_recommendation(edge, confidence, T)

        return PricingResult(
            theoretical_price=theoretical,
            market_price=market_price,
            mispricing=mispricing,
            mispricing_pct=mispricing_pct,
            edge=edge,
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
            implied_vol=implied_vol,
            confidence=confidence,
            recommendation=recommendation
        )

    def gamma(self, S: float, K: float, T: float, sigma: float) -> float:
        """计算 Gamma"""
        if T <= 0 or sigma <= 0:
            return 0
        d1 = self.d1(S, K, T, sigma)
        d2 = self.d2(S, K, T, sigma)
        gamma = -math.exp(-self.r * T) * self.norm_pdf(d2) * d1 / (S ** 2 * sigma ** 2 * T)
        return gamma

    def _calculate_confidence(self, mispricing: float, T: float, sigma: float) -> float:
        """计算置信度"""
        mispricing_conf = min(1.0, abs(mispricing) * 5)
        time_conf = max(0.3, 1.0 - T)
        vol_conf = max(0.3, 1.0 - sigma / 2)
        confidence = (mispricing_conf * 0.5 + time_conf * 0.25 + vol_conf * 0.25)
        return round(confidence, 3)

    def _generate_recommendation(self, edge: float, confidence: float, T: float) -> str:
        """生成交易推荐"""
        if T < 1/24/60:  # 小于1分钟
            return "⚠️ 临近到期，不建议交易"

        if confidence < 0.4:
            return "❌ 置信度过低，不建议交易"

        if edge > 0.03:
            return f"✅ 强烈买入信号 (Edge: {edge:.2%})"
        elif edge > 0.01:
            return f"💡 可考虑买入 (Edge: {edge:.2%})"
        elif edge > 0:
            return f"🔍 微小优势 (Edge: {edge:.2%})，谨慎交易"
        else:
            return f"⛔ 无优势 (Edge: {edge:.2%})，不建议买入"


class VolatilityEstimator:
    """
    波动率估算器

    使用多种方法估算隐含波动率
    """

    @staticmethod
    def historical_volatility(prices: list, window: int = 20) -> float:
        """计算历史波动率"""
        if len(prices) < window:
            return 0.5

        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0 and prices[i] > 0:
                ret = math.log(prices[i] / prices[i-1])
                returns.append(ret)

        if len(returns) < 2:
            return 0.5

        recent_returns = returns[-window:]
        mean = sum(recent_returns) / len(recent_returns)
        variance = sum((r - mean) ** 2 for r in recent_returns) / (len(recent_returns) - 1)
        std = math.sqrt(variance)
        annualized_vol = std * math.sqrt(525600)  # 年化

        return annualized_vol

    @staticmethod
    def parkinson_volatility(high_prices: list, low_prices: list, window: int = 20) -> float:
        """Parkinson 波动率估算 (基于高低价)"""
        if len(high_prices) < window or len(low_prices) < window:
            return 0.5

        highs = high_prices[-window:]
        lows = low_prices[-window:]

        total = 0
        for h, l in zip(highs, lows):
            if h > 0 and l > 0:
                total += (math.log(h / l)) ** 2

        vol = math.sqrt(total / (window * 4 * math.log(2)))
        annualized = vol * math.sqrt(525600)

        return annualized


class BinaryOptionsPricer:
    """
    二元期权定价器

    整合定价模型和波动率估算
    """

    def __init__(self):
        self.bs_model = BlackScholesBinary()
        self.vol_estimator = VolatilityEstimator()

    def analyze_market(self, current_price: float, target_price: float,
                      time_to_expiry: float, market_yes_price: float,
                      historical_prices: list = None,
                      high_prices: list = None, low_prices: list = None,
                      fee_rate: float = 0.02) -> Tuple[PricingResult, PricingResult]:
        """
        分析一个涨跌市场
        """
        # 估算波动率
        if historical_prices and len(historical_prices) > 20:
            sigma = self.vol_estimator.historical_volatility(historical_prices)
        elif high_prices and low_prices:
            sigma = self.vol_estimator.parkinson_volatility(high_prices, low_prices)
        else:
            sigma = 0.5  # 默认波动率

        # 分析 Yes (看涨)
        yes_result = self.bs_model.price_binary_option(
            S=current_price,
            K=target_price,
            T=time_to_expiry,
            sigma=sigma,
            market_price=market_yes_price,
            option_type=OptionType.CALL,
            fee_rate=fee_rate
        )

        # 分析 No (看跌)
        no_result = self.bs_model.price_binary_option(
            S=current_price,
            K=target_price,
            T=time_to_expiry,
            sigma=sigma,
            market_price=1 - market_yes_price,
            option_type=OptionType.PUT,
            fee_rate=fee_rate
        )

        return yes_result, no_result

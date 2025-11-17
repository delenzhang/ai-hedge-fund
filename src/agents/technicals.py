import math

from langchain_core.messages import HumanMessage
from longport.openapi import Period

from src.graph.state import AgentState, show_agent_reasoning
from src.utils.api_key import get_api_key_from_state
import json
import pandas as pd
import numpy as np

from src.tools.api import get_prices, prices_to_df
from src.utils.progress import progress


def safe_float(value, default=0.0):
    """
    安全地将值转换为浮点数，处理NaN情况
    
    用于处理pandas和numpy计算中可能出现的NaN值，确保返回有效的浮点数。
    这在技术指标计算中非常重要，因为某些计算可能产生无效值。
    
    Args:
        value: 要转换的值（可以是pandas标量、numpy值等）
        default: 如果输入是NaN或无效时返回的默认值
    
    Returns:
        float: 转换后的值，如果输入无效则返回默认值
    """
    try:
        if pd.isna(value) or np.isnan(value):
            return default
        return float(value)
    except (ValueError, TypeError, OverflowError):
        return default


##### Technical Analyst #####
def technical_analyst_agent(state: AgentState, agent_id: str = "technical_analyst_agent"):
    """
    技术分析智能体：结合多种交易策略的综合技术分析系统
    
    该系统对多个股票代码进行全面的技术分析，包括：
    1. 趋势跟踪（Trend Following）- 识别并跟随市场趋势
    2. 均值回归（Mean Reversion）- 识别价格偏离均值的回归机会
    3. 动量分析（Momentum）- 分析价格和成交量的动量变化
    4. 波动率分析（Volatility Analysis）- 评估市场波动率和风险
    5. 统计套利信号（Statistical Arbitrage Signals）- 基于统计特性的交易信号
    6. 多周期K线分析（Daily & Hourly K-line Analysis）- 日线和小时线的综合分析
    
    Args:
        state: 智能体状态，包含股票代码、日期范围等数据
        agent_id: 智能体标识符，默认为 "technical_analyst_agent"
    
    Returns:
        dict: 更新后的状态，包含技术分析结果和消息
    """
    data = state["data"]
    start_date = data["start_date"]
    end_date = data["end_date"]
    tickers = data["tickers"]
    api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
    # Initialize analysis for each ticker
    technical_analysis = {}

    for ticker in tickers:
        progress.update_status(agent_id, ticker, "Analyzing price data")

        # Get the historical price data
        prices = get_prices(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            api_key=api_key,
        )

        if not prices:
            progress.update_status(agent_id, ticker, "Failed: No price data found")
            continue

        # Convert prices to a DataFrame
        prices_df = prices_to_df(prices)

        progress.update_status(agent_id, ticker, "Calculating trend signals")
        trend_signals = calculate_trend_signals(prices_df)

        progress.update_status(agent_id, ticker, "Calculating mean reversion")
        mean_reversion_signals = calculate_mean_reversion_signals(prices_df)

        progress.update_status(agent_id, ticker, "Calculating momentum")
        momentum_signals = calculate_momentum_signals(prices_df)

        progress.update_status(agent_id, ticker, "Analyzing volatility")
        volatility_signals = calculate_volatility_signals(prices_df)

        progress.update_status(agent_id, ticker, "Statistical analysis")
        stat_arb_signals = calculate_stat_arb_signals(prices_df)

        # 新增：多周期K线分析（日线+小时线）
        progress.update_status(agent_id, ticker, "Analyzing daily K-line")
        daily_analysis = analyze_daily_kline(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            api_key=api_key,
        )

        progress.update_status(agent_id, ticker, "Analyzing hourly K-line")
        hourly_analysis = analyze_hourly_kline(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            api_key=api_key,
            daily_strategy=daily_analysis.get("strategy", "neutral"),
        )

        # Combine all signals using a weighted ensemble approach
        strategy_weights = {
            "trend": 0.25,
            "mean_reversion": 0.20,
            "momentum": 0.25,
            "volatility": 0.15,
            "stat_arb": 0.15,
        }

        progress.update_status(agent_id, ticker, "Combining signals")
        combined_signal = weighted_signal_combination(
            {
                "trend": trend_signals,
                "mean_reversion": mean_reversion_signals,
                "momentum": momentum_signals,
                "volatility": volatility_signals,
                "stat_arb": stat_arb_signals,
            },
            strategy_weights,
        )

        # Generate detailed analysis report for this ticker
        technical_analysis[ticker] = {
            "signal": combined_signal["signal"],
            "confidence": round(combined_signal["confidence"] * 100),
            "reasoning": {
                "trend_following": {
                    "signal": trend_signals["signal"],
                    "confidence": round(trend_signals["confidence"] * 100),
                    "metrics": normalize_pandas(trend_signals["metrics"]),
                },
                "mean_reversion": {
                    "signal": mean_reversion_signals["signal"],
                    "confidence": round(mean_reversion_signals["confidence"] * 100),
                    "metrics": normalize_pandas(mean_reversion_signals["metrics"]),
                },
                "momentum": {
                    "signal": momentum_signals["signal"],
                    "confidence": round(momentum_signals["confidence"] * 100),
                    "metrics": normalize_pandas(momentum_signals["metrics"]),
                },
                "volatility": {
                    "signal": volatility_signals["signal"],
                    "confidence": round(volatility_signals["confidence"] * 100),
                    "metrics": normalize_pandas(volatility_signals["metrics"]),
                },
                "statistical_arbitrage": {
                    "signal": stat_arb_signals["signal"],
                    "confidence": round(stat_arb_signals["confidence"] * 100),
                    "metrics": normalize_pandas(stat_arb_signals["metrics"]),
                },
                # 新增：多周期K线分析结果（需要规范化以支持JSON序列化）
                "daily_kline_analysis": normalize_pandas(daily_analysis),
                "hourly_kline_analysis": normalize_pandas(hourly_analysis),
            },
        }
        progress.update_status(agent_id, ticker, "Done", analysis=json.dumps(technical_analysis, indent=4))

    # Create the technical analyst message
    message = HumanMessage(
        content=json.dumps(technical_analysis),
        name=agent_id,
    )

    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(technical_analysis, "Technical Analyst")

    # Add the signal to the analyst_signals list
    state["data"]["analyst_signals"][agent_id] = technical_analysis

    progress.update_status(agent_id, None, "Done")

    return {
        "messages": state["messages"] + [message],
        "data": data,
    }


def calculate_trend_signals(prices_df):
    """
    计算趋势跟踪信号
    
    使用多时间框架和多个技术指标来判断市场趋势方向和强度。
    主要使用指数移动平均线（EMA）和平均趋向指标（ADX）来判断趋势。
    
    Args:
        prices_df: 包含OHLCV数据的DataFrame
    
    Returns:
        dict: 包含以下字段：
            - signal: 趋势信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 信心度 (0-1之间)
            - metrics: 技术指标详情（ADX值、趋势强度等）
    """
    # Calculate EMAs for multiple timeframes
    ema_8 = calculate_ema(prices_df, 8)
    ema_21 = calculate_ema(prices_df, 21)
    ema_55 = calculate_ema(prices_df, 55)

    # Calculate ADX for trend strength
    adx = calculate_adx(prices_df, 14)

    # Determine trend direction and strength
    short_trend = ema_8 > ema_21
    medium_trend = ema_21 > ema_55

    # Combine signals with confidence weighting
    trend_strength = adx["adx"].iloc[-1] / 100.0

    if short_trend.iloc[-1] and medium_trend.iloc[-1]:
        signal = "bullish"
        confidence = trend_strength
    elif not short_trend.iloc[-1] and not medium_trend.iloc[-1]:
        signal = "bearish"
        confidence = trend_strength
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "adx": safe_float(adx["adx"].iloc[-1]),
            "trend_strength": safe_float(trend_strength),
        },
    }


def calculate_mean_reversion_signals(prices_df):
    """
    计算均值回归信号
    
    使用统计方法和布林带（Bollinger Bands）来识别价格偏离均值后的回归机会。
    当价格大幅偏离移动平均线时，可能出现回归均值的交易机会。
    
    Args:
        prices_df: 包含OHLCV数据的DataFrame
    
    Returns:
        dict: 包含以下字段：
            - signal: 回归信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 信心度 (0-1之间)
            - metrics: 技术指标详情（Z-score、RSI、布林带位置等）
    """
    # Calculate z-score of price relative to moving average
    ma_50 = prices_df["close"].rolling(window=50).mean()
    std_50 = prices_df["close"].rolling(window=50).std()
    z_score = (prices_df["close"] - ma_50) / std_50

    # Calculate Bollinger Bands
    bb_upper, bb_lower = calculate_bollinger_bands(prices_df)

    # Calculate RSI with multiple timeframes
    rsi_14 = calculate_rsi(prices_df, 14)
    rsi_28 = calculate_rsi(prices_df, 28)

    # Mean reversion signals
    price_vs_bb = (prices_df["close"].iloc[-1] - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])

    # Combine signals
    if z_score.iloc[-1] < -2 and price_vs_bb < 0.2:
        signal = "bullish"
        confidence = min(abs(z_score.iloc[-1]) / 4, 1.0)
    elif z_score.iloc[-1] > 2 and price_vs_bb > 0.8:
        signal = "bearish"
        confidence = min(abs(z_score.iloc[-1]) / 4, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "z_score": safe_float(z_score.iloc[-1]),
            "price_vs_bb": safe_float(price_vs_bb),
            "rsi_14": safe_float(rsi_14.iloc[-1]),
            "rsi_28": safe_float(rsi_28.iloc[-1]),
        },
    }


def calculate_momentum_signals(prices_df):
    """
    计算动量信号
    
    多因子动量策略，综合考虑价格动量和成交量动量。
    通过分析不同时间周期的收益率和成交量变化来判断市场动量。
    
    Args:
        prices_df: 包含OHLCV数据的DataFrame
    
    Returns:
        dict: 包含以下字段：
            - signal: 动量信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 信心度 (0-1之间)
            - metrics: 动量指标详情（1月、3月、6月动量，成交量动量等）
    """
    # Price momentum
    returns = prices_df["close"].pct_change()
    mom_1m = returns.rolling(21).sum()
    mom_3m = returns.rolling(63).sum()
    mom_6m = returns.rolling(126).sum()

    # Volume momentum
    volume_ma = prices_df["volume"].rolling(21).mean()
    volume_momentum = prices_df["volume"] / volume_ma

    # Relative strength
    # (would compare to market/sector in real implementation)

    # Calculate momentum score
    momentum_score = (0.4 * mom_1m + 0.3 * mom_3m + 0.3 * mom_6m).iloc[-1]

    # Volume confirmation
    volume_confirmation = volume_momentum.iloc[-1] > 1.0

    if momentum_score > 0.05 and volume_confirmation:
        signal = "bullish"
        confidence = min(abs(momentum_score) * 5, 1.0)
    elif momentum_score < -0.05 and volume_confirmation:
        signal = "bearish"
        confidence = min(abs(momentum_score) * 5, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "momentum_1m": safe_float(mom_1m.iloc[-1]),
            "momentum_3m": safe_float(mom_3m.iloc[-1]),
            "momentum_6m": safe_float(mom_6m.iloc[-1]),
            "volume_momentum": safe_float(volume_momentum.iloc[-1]),
        },
    }


def calculate_volatility_signals(prices_df):
    """
    计算波动率信号
    
    基于波动率的交易策略，通过分析历史波动率和波动率制度来判断交易机会。
    低波动率可能预示着波动率扩张，高波动率可能预示着波动率收缩。
    
    Args:
        prices_df: 包含OHLCV数据的DataFrame
    
    Returns:
        dict: 包含以下字段：
            - signal: 波动率信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 信心度 (0-1之间)
            - metrics: 波动率指标详情（历史波动率、波动率制度、ATR比率等）
    """
    # Calculate various volatility metrics
    returns = prices_df["close"].pct_change()

    # Historical volatility
    hist_vol = returns.rolling(21).std() * math.sqrt(252)

    # Volatility regime detection
    vol_ma = hist_vol.rolling(63).mean()
    vol_regime = hist_vol / vol_ma

    # Volatility mean reversion
    vol_z_score = (hist_vol - vol_ma) / hist_vol.rolling(63).std()

    # ATR ratio
    atr = calculate_atr(prices_df)
    atr_ratio = atr / prices_df["close"]

    # Generate signal based on volatility regime
    current_vol_regime = vol_regime.iloc[-1]
    vol_z = vol_z_score.iloc[-1]

    if current_vol_regime < 0.8 and vol_z < -1:
        signal = "bullish"  # Low vol regime, potential for expansion
        confidence = min(abs(vol_z) / 3, 1.0)
    elif current_vol_regime > 1.2 and vol_z > 1:
        signal = "bearish"  # High vol regime, potential for contraction
        confidence = min(abs(vol_z) / 3, 1.0)
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "historical_volatility": safe_float(hist_vol.iloc[-1]),
            "volatility_regime": safe_float(current_vol_regime),
            "volatility_z_score": safe_float(vol_z),
            "atr_ratio": safe_float(atr_ratio.iloc[-1]),
        },
    }


def calculate_stat_arb_signals(prices_df):
    """
    计算统计套利信号
    
    基于价格行为分析的统计套利信号。
    通过分析价格分布的统计特性（偏度、峰度）和Hurst指数来判断均值回归或趋势延续的可能性。
    
    Args:
        prices_df: 包含OHLCV数据的DataFrame
    
    Returns:
        dict: 包含以下字段：
            - signal: 统计套利信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 信心度 (0-1之间)
            - metrics: 统计指标详情（Hurst指数、偏度、峰度等）
    """
    # Calculate price distribution statistics
    returns = prices_df["close"].pct_change()

    # Skewness and kurtosis
    skew = returns.rolling(63).skew()
    kurt = returns.rolling(63).kurt()

    # Test for mean reversion using Hurst exponent
    hurst = calculate_hurst_exponent(prices_df["close"])

    # Correlation analysis
    # (would include correlation with related securities in real implementation)

    # Generate signal based on statistical properties
    if hurst < 0.4 and skew.iloc[-1] > 1:
        signal = "bullish"
        confidence = (0.5 - hurst) * 2
    elif hurst < 0.4 and skew.iloc[-1] < -1:
        signal = "bearish"
        confidence = (0.5 - hurst) * 2
    else:
        signal = "neutral"
        confidence = 0.5

    return {
        "signal": signal,
        "confidence": confidence,
        "metrics": {
            "hurst_exponent": safe_float(hurst),
            "skewness": safe_float(skew.iloc[-1]),
            "kurtosis": safe_float(kurt.iloc[-1]),
        },
    }


def weighted_signal_combination(signals, weights):
    """
    加权组合多个交易信号
    
    将不同策略产生的交易信号按照预设权重进行加权组合，得出最终的综合信号。
    这种方法可以平衡不同策略的优势，提高信号的可靠性。
    
    Args:
        signals: 字典，包含各个策略的信号（如trend、mean_reversion等）
        weights: 字典，包含各个策略的权重（权重之和应该接近1.0）
    
    Returns:
        dict: 包含以下字段：
            - signal: 综合信号 ("bullish"看涨, "bearish"看跌, "neutral"中性)
            - confidence: 综合信心度 (0-1之间)
    """
    # Convert signals to numeric values
    signal_values = {"bullish": 1, "neutral": 0, "bearish": -1}

    weighted_sum = 0
    total_confidence = 0

    for strategy, signal in signals.items():
        numeric_signal = signal_values[signal["signal"]]
        weight = weights[strategy]
        confidence = signal["confidence"]

        weighted_sum += numeric_signal * weight * confidence
        total_confidence += weight * confidence

    # Normalize the weighted sum
    if total_confidence > 0:
        final_score = weighted_sum / total_confidence
    else:
        final_score = 0

    # Convert back to signal
    if final_score > 0.2:
        signal = "bullish"
    elif final_score < -0.2:
        signal = "bearish"
    else:
        signal = "neutral"

    return {"signal": signal, "confidence": abs(final_score)}


def normalize_pandas(obj):
    """
    将pandas Series/DataFrame和numpy类型转换为原生Python类型
    
    用于将技术分析结果中的pandas和numpy对象转换为可序列化的Python原生类型，
    以便在JSON中正确存储和传输。
    
    Args:
        obj: 要转换的对象（可以是Series、DataFrame、dict、list、numpy类型等）
    
    Returns:
        转换后的Python原生类型对象
    """
    # 处理numpy类型
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj) if isinstance(obj, np.floating) else int(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    # 处理pandas类型
    elif isinstance(obj, pd.Series):
        return obj.tolist()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict("records")
    # 处理字典和列表
    elif isinstance(obj, dict):
        return {k: normalize_pandas(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [normalize_pandas(item) for item in obj]
    return obj


def calculate_rsi(prices_df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算相对强弱指标（RSI）
    
    RSI是衡量价格动量强度的技术指标，范围在0-100之间。
    RSI > 70通常表示超买，RSI < 30通常表示超卖。
    
    Args:
        prices_df: 包含收盘价数据的DataFrame
        period: RSI计算周期，默认为14
    
    Returns:
        pd.Series: RSI值序列
    """
    delta = prices_df["close"].diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_bollinger_bands(prices_df: pd.DataFrame, window: int = 20) -> tuple[pd.Series, pd.Series]:
    """
    计算布林带（Bollinger Bands）
    
    布林带由三条线组成：中轨（移动平均线）、上轨（中轨+2倍标准差）、下轨（中轨-2倍标准差）。
    价格接近上轨可能表示超买，接近下轨可能表示超卖。
    
    Args:
        prices_df: 包含收盘价数据的DataFrame
        window: 移动平均窗口，默认为20
    
    Returns:
        tuple: (上轨, 下轨) 两个Series
    """
    sma = prices_df["close"].rolling(window).mean()
    std_dev = prices_df["close"].rolling(window).std()
    upper_band = sma + (std_dev * 2)
    lower_band = sma - (std_dev * 2)
    return upper_band, lower_band


def calculate_ema(df: pd.DataFrame, window: int) -> pd.Series:
    """
    计算指数移动平均线（EMA）
    
    EMA对近期价格给予更高权重，比简单移动平均线（SMA）对价格变化更敏感。
    常用于趋势跟踪和交易信号生成。
    
    Args:
        df: 包含价格数据的DataFrame
        window: EMA周期（例如：8、21、55等）
    
    Returns:
        pd.Series: EMA值序列
    """
    return df["close"].ewm(span=window, adjust=False).mean()


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    计算平均趋向指标（ADX）
    
    ADX用于衡量趋势的强度，而不是趋势的方向。
    ADX值越高，表示趋势越强；ADX值越低，表示市场处于震荡状态。
    通常ADX > 25表示强趋势，ADX < 20表示弱趋势或震荡。
    
    Args:
        df: 包含OHLC（开高低收）数据的DataFrame
        period: 计算周期，默认为14
    
    Returns:
        DataFrame: 包含ADX、+DI、-DI值的DataFrame
    """
    # Calculate True Range
    df["high_low"] = df["high"] - df["low"]
    df["high_close"] = abs(df["high"] - df["close"].shift())
    df["low_close"] = abs(df["low"] - df["close"].shift())
    df["tr"] = df[["high_low", "high_close", "low_close"]].max(axis=1)

    # Calculate Directional Movement
    df["up_move"] = df["high"] - df["high"].shift()
    df["down_move"] = df["low"].shift() - df["low"]

    df["plus_dm"] = np.where((df["up_move"] > df["down_move"]) & (df["up_move"] > 0), df["up_move"], 0)
    df["minus_dm"] = np.where((df["down_move"] > df["up_move"]) & (df["down_move"] > 0), df["down_move"], 0)

    # Calculate ADX
    df["+di"] = 100 * (df["plus_dm"].ewm(span=period).mean() / df["tr"].ewm(span=period).mean())
    df["-di"] = 100 * (df["minus_dm"].ewm(span=period).mean() / df["tr"].ewm(span=period).mean())
    df["dx"] = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])
    df["adx"] = df["dx"].ewm(span=period).mean()

    return df[["adx", "+di", "-di"]]


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算平均真实波幅（ATR）
    
    ATR用于衡量市场波动率，反映价格在一定时期内的平均波动幅度。
    ATR值越大，表示市场波动越剧烈；ATR值越小，表示市场波动越平缓。
    常用于设置止损位和评估市场风险。
    
    Args:
        df: 包含OHLC（开高低收）数据的DataFrame
        period: ATR计算周期，默认为14
    
    Returns:
        pd.Series: ATR值序列
    """
    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.rolling(period).mean()


def calculate_hurst_exponent(price_series: pd.Series, max_lag: int = 20) -> float:
    """
    Calculate Hurst Exponent to determine long-term memory of time series
    H < 0.5: Mean reverting series
    H = 0.5: Random walk
    H > 0.5: Trending series

    Args:
        price_series: Array-like price data
        max_lag: Maximum lag for R/S calculation

    Returns:
        float: Hurst exponent
    """
    lags = range(2, max_lag)
    # Add small epsilon to avoid log(0)
    tau = [max(1e-8, np.sqrt(np.std(np.subtract(price_series[lag:], price_series[:-lag])))) for lag in lags]

    # Return the Hurst exponent from linear fit
    try:
        reg = np.polyfit(np.log(lags), np.log(tau), 1)
        return reg[0]  # Hurst exponent is the slope
    except (ValueError, RuntimeWarning):
        # Return 0.5 (random walk) if calculation fails
        return 0.5


def analyze_daily_kline(ticker: str, start_date: str, end_date: str, api_key: str = None) -> dict:
    """
    第一步：日线K线分析
    
    分析日线级别的整体趋势和量价关系，做出战略决策。
    这是多周期分析的第一步，用于确定整体交易方向。
    
    Args:
        ticker: 股票代码
        start_date: 开始日期，格式为 "YYYY-MM-DD"
        end_date: 结束日期，格式为 "YYYY-MM-DD"
        api_key: API密钥（可选）
    
    Returns:
        dict: 包含以下字段的分析结果：
            - trend_type: 趋势类型 ("uptrend"上升通道, "downtrend"下降通道, "sideways"震荡箱体)
            - trend_strength: 趋势强度 (0-100)
            - price_volume_relation: 量价关系 ("healthy"健康, "divergence"量价背离)
            - volume_analysis: 成交量分析详情
            - strategy: 战略决策 ("long"做多, "short"做空, "neutral"观望)
            - confidence: 信心度 (0-100)
            - metrics: 技术指标详情
    """
    # 获取日线K线数据
    daily_prices = get_prices(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        period=Period.Day,  # 使用日线周期
        api_key=api_key,
    )
    
    if not daily_prices or len(daily_prices) < 20:
        return {
            "trend_type": "unknown",
            "trend_strength": 0,
            "price_volume_relation": "unknown",
            "volume_analysis": {},
            "strategy": "neutral",
            "confidence": 0,
            "metrics": {},
            "error": "Insufficient daily data",
        }
    
    # 转换为DataFrame便于分析
    daily_df = prices_to_df(daily_prices)
    
    # 1. 判断整体趋势：上升通道、下降通道还是震荡箱体
    # 计算多条均线来判断趋势
    ma_20 = daily_df["close"].rolling(window=20).mean()
    ma_60 = daily_df["close"].rolling(window=60).mean()
    
    # 计算最近一段时间的趋势
    recent_period = min(30, len(daily_df))  # 最近30个交易日
    recent_highs = daily_df["high"].tail(recent_period)
    recent_lows = daily_df["low"].tail(recent_period)
    
    # 判断趋势类型
    current_price = daily_df["close"].iloc[-1]
    price_20_ago = daily_df["close"].iloc[-min(20, len(daily_df)-1)] if len(daily_df) > 1 else current_price
    
    # 计算趋势强度：基于价格变化幅度和均线排列
    price_change_pct = (current_price - price_20_ago) / price_20_ago if price_20_ago > 0 else 0
    
    # 均线排列判断（确保返回Python原生bool类型）
    ma_bullish = False
    ma_bearish = False
    if len(ma_20) > 0 and len(ma_60) > 0:
        ma_bullish = bool(ma_20.iloc[-1] > ma_60.iloc[-1] and current_price > ma_20.iloc[-1])
        ma_bearish = bool(ma_20.iloc[-1] < ma_60.iloc[-1] and current_price < ma_20.iloc[-1])
    
    # 判断趋势类型
    if ma_bullish and price_change_pct > 0.05:  # 上涨超过5%且均线多头排列
        trend_type = "uptrend"
        trend_strength = min(100, abs(price_change_pct) * 1000)  # 转换为0-100的强度
    elif ma_bearish and price_change_pct < -0.05:  # 下跌超过5%且均线空头排列
        trend_type = "downtrend"
        trend_strength = min(100, abs(price_change_pct) * 1000)
    else:
        # 震荡箱体：计算最高价和最低价的波动范围
        price_range = (recent_highs.max() - recent_lows.min()) / recent_lows.min() if recent_lows.min() > 0 else 0
        if price_range < 0.15:  # 波动范围小于15%，认为是震荡
            trend_type = "sideways"
            trend_strength = 50  # 震荡趋势强度中等
        else:
            # 根据价格变化方向判断
            if price_change_pct > 0.02:
                trend_type = "uptrend"
                trend_strength = min(100, abs(price_change_pct) * 1000)
            elif price_change_pct < -0.02:
                trend_type = "downtrend"
                trend_strength = min(100, abs(price_change_pct) * 1000)
            else:
                trend_type = "sideways"
                trend_strength = 50
    
    # 2. 观察量价关系：价涨量增、价跌量缩 vs 量价背离
    # 计算近期价格和成交量的相关性
    recent_df = daily_df.tail(min(20, len(daily_df)))
    
    # 计算价格变化和成交量变化
    price_changes = recent_df["close"].pct_change().dropna()
    volume_changes = recent_df["volume"].pct_change().dropna()
    
    # 对齐数据
    min_len = min(len(price_changes), len(volume_changes))
    if min_len > 5:
        price_changes = price_changes.tail(min_len)
        volume_changes = volume_changes.tail(min_len)
        
        # 计算量价相关性（确保返回Python原生类型）
        correlation = safe_float(price_changes.corr(volume_changes)) if len(price_changes) > 1 else 0.0
        
        # 判断量价关系
        if correlation > 0.3:
            # 正相关：价涨量增、价跌量缩（健康）
            price_volume_relation = "healthy"
        elif correlation < -0.3:
            # 负相关：量价背离
            price_volume_relation = "divergence"
        else:
            # 相关性较弱
            price_volume_relation = "weak"
    else:
        price_volume_relation = "unknown"
        correlation = 0
    
    # 详细分析最近几天的量价关系
    volume_analysis = {}
    if len(recent_df) >= 5:
        # 最近5天的量价分析（确保返回Python原生类型）
        last_5 = recent_df.tail(5)
        price_up_days = int((last_5["close"] > last_5["close"].shift(1)).sum())
        volume_up_on_price_up = 0
        volume_down_on_price_down = 0
        
        for i in range(1, len(last_5)):
            if last_5["close"].iloc[i] > last_5["close"].iloc[i-1]:
                # 价格上涨
                if last_5["volume"].iloc[i] > last_5["volume"].iloc[i-1]:
                    volume_up_on_price_up += 1
            elif last_5["close"].iloc[i] < last_5["close"].iloc[i-1]:
                # 价格下跌
                if last_5["volume"].iloc[i] < last_5["volume"].iloc[i-1]:
                    volume_down_on_price_down += 1
        
        volume_analysis = {
            "price_volume_correlation": safe_float(correlation),
            "volume_up_on_price_up_days": int(volume_up_on_price_up),
            "volume_down_on_price_down_days": int(volume_down_on_price_down),
            "avg_volume_ratio": safe_float(recent_df["volume"].tail(5).mean() / recent_df["volume"].tail(20).mean() if len(recent_df) >= 20 else 1.0),
        }
    
    # 3. 做出战略决策
    # 基于趋势和量价关系确定交易策略
    strategy = "neutral"
    confidence = 50
    
    if trend_type == "uptrend" and price_volume_relation == "healthy":
        # 上升趋势 + 健康量价关系 = 做多
        strategy = "long"
        confidence = min(100, int(trend_strength + 20))
    elif trend_type == "uptrend" and price_volume_relation == "divergence":
        # 上升趋势但量价背离 = 谨慎做多或观望
        strategy = "long"
        confidence = max(30, int(trend_strength - 20))
    elif trend_type == "downtrend" and price_volume_relation == "healthy":
        # 下降趋势 + 健康量价关系 = 做空
        strategy = "short"
        confidence = min(100, int(trend_strength + 20))
    elif trend_type == "downtrend" and price_volume_relation == "divergence":
        # 下降趋势但量价背离 = 谨慎做空或观望
        strategy = "short"
        confidence = max(30, int(trend_strength - 20))
    elif trend_type == "sideways":
        # 震荡行情 = 观望或区间交易
        strategy = "neutral"
        confidence = 40
    
    # 检查是否有突破信号（放量突破盘整平台）
    if len(daily_df) >= 20:
        recent_high = recent_highs.max()
        recent_low = recent_lows.min()
        price_range_pct = (recent_high - recent_low) / recent_low if recent_low > 0 else 0
        
        # 如果当前价格突破近期高点且放量
        avg_volume_20 = daily_df["volume"].tail(20).mean()
        current_volume = daily_df["volume"].iloc[-1]
        
        if current_price > recent_high * 0.98 and current_volume > avg_volume_20 * 1.5:
            # 放量突破，强化做多信号
            if strategy == "long":
                confidence = min(100, confidence + 15)
            elif strategy == "neutral":
                strategy = "long"
                confidence = 60
    
    return {
        "trend_type": trend_type,
        "trend_strength": round(safe_float(trend_strength)),
        "price_volume_relation": price_volume_relation,
        "volume_analysis": volume_analysis,
        "strategy": strategy,
        "confidence": round(confidence),
        "metrics": {
            "ma_20": safe_float(ma_20.iloc[-1] if len(ma_20) > 0 else 0),
            "ma_60": safe_float(ma_60.iloc[-1] if len(ma_60) > 0 else 0),
            "current_price": safe_float(current_price),
            "price_change_20d_pct": safe_float(price_change_pct * 100),
            "recent_high": safe_float(recent_highs.max()),
            "recent_low": safe_float(recent_lows.min()),
        },
    }


def analyze_hourly_kline(
    ticker: str,
    start_date: str,
    end_date: str,
    api_key: str = None,
    daily_strategy: str = "neutral",
) -> dict:
    """
    第二步：小时线K线分析
    
    在日线战略决策的基础上，切换到60分钟K线图寻找战术买入点。
    等待技术性回调，观察成交量萎缩，寻找止跌K线信号。
    
    Args:
        ticker: 股票代码
        start_date: 开始日期，格式为 "YYYY-MM-DD"
        end_date: 结束日期，格式为 "YYYY-MM-DD"
        api_key: API密钥（可选）
        daily_strategy: 日线分析得出的战略决策 ("long"做多, "short"做空, "neutral"观望)
    
    Returns:
        dict: 包含以下字段的分析结果：
            - tactical_signal: 战术信号 ("buy"买入, "sell"卖出, "wait"等待)
            - entry_point_detected: 是否检测到买入点
            - pullback_analysis: 回调分析详情
            - volume_analysis: 成交量分析
            - candlestick_patterns: K线形态识别
            - confidence: 信心度 (0-100)
            - metrics: 技术指标详情
    """
    # 获取60分钟K线数据
    hourly_prices = get_prices(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        period=Period.Min_60,  # 使用60分钟周期
        api_key=api_key,
    )
    
    if not hourly_prices or len(hourly_prices) < 20:
        return {
            "tactical_signal": "wait",
            "entry_point_detected": False,
            "pullback_analysis": {},
            "volume_analysis": {},
            "candlestick_patterns": {},
            "confidence": 0,
            "metrics": {},
            "error": "Insufficient hourly data",
        }
    
    # 转换为DataFrame便于分析
    hourly_df = prices_to_df(hourly_prices)
    
    # 计算均线（小时线的MA20和MA60对应约20小时和60小时）
    ma_20 = hourly_df["close"].rolling(window=20).mean()
    ma_60 = hourly_df["close"].rolling(window=60).mean()
    
    # 1. 等待技术性回调（回踩MA20或MA60均线）
    current_price = hourly_df["close"].iloc[-1]
    current_ma20 = ma_20.iloc[-1] if len(ma_20) > 0 else current_price
    current_ma60 = ma_60.iloc[-1] if len(ma_60) > 0 else current_price
    
    # 判断是否在均线附近（允许2%的误差，确保返回Python原生bool类型）
    near_ma20 = bool(abs(current_price - current_ma20) / current_ma20 < 0.02) if current_ma20 > 0 else False
    near_ma60 = bool(abs(current_price - current_ma60) / current_ma60 < 0.02) if current_ma60 > 0 else False
    
    # 判断是否刚刚回踩均线（最近几根K线从上方接近均线）
    pullback_detected = False
    pullback_type = None
    pullback_strength = 0
    
    if len(hourly_df) >= 5:
        recent_5 = hourly_df.tail(5)
        recent_ma20 = ma_20.tail(5) if len(ma_20) >= 5 else pd.Series([current_ma20] * 5)
        
        # 检查是否从上方回踩MA20（确保返回Python原生类型）
        prices_above_ma = int((recent_5["close"] > recent_ma20).sum())
        if prices_above_ma >= 3 and near_ma20:
            # 之前价格在均线上方，现在接近均线 = 回踩
            pullback_detected = True
            pullback_type = "ma20"
            pullback_strength = 60
        
        # 检查是否从上方回踩MA60（确保返回Python原生类型）
        if len(ma_60) >= 5:
            recent_ma60 = ma_60.tail(5)
            prices_above_ma60 = int((recent_5["close"] > recent_ma60).sum())
            if prices_above_ma60 >= 3 and near_ma60:
                pullback_detected = True
                pullback_type = "ma60"
                pullback_strength = 80  # MA60回踩更强
    
    # 2. 观察回调时的成交量是否显著萎缩
    volume_analysis = {}
    volume_shrinking = False
    
    if len(hourly_df) >= 10:
        # 计算最近5根K线的平均成交量 vs 之前5根K线的平均成交量
        recent_5_volume = hourly_df["volume"].tail(5).mean()
        previous_5_volume = hourly_df["volume"].tail(10).head(5).mean()
        
        volume_ratio = recent_5_volume / previous_5_volume if previous_5_volume > 0 else 1.0
        
        # 成交量萎缩：当前成交量小于之前的70%（确保返回Python原生bool类型）
        volume_shrinking = bool(volume_ratio < 0.7)
        
        volume_analysis = {
            "recent_5_avg_volume": safe_float(recent_5_volume),
            "previous_5_avg_volume": safe_float(previous_5_volume),
            "volume_ratio": safe_float(volume_ratio),
            "volume_shrinking": volume_shrinking,
        }
    
    # 3. 识别止跌K线信号（阳包阴、锤子线等）
    candlestick_patterns = {}
    reversal_signal = False
    reversal_pattern = None
    
    if len(hourly_df) >= 3:
        # 获取最近几根K线
        last_3 = hourly_df.tail(3)
        
        # 检查阳包阴形态（当前阳线完全包含前一根阴线）
        if len(last_3) >= 2:
            prev_candle = last_3.iloc[-2]
            curr_candle = last_3.iloc[-1]
            
            # 阳包阴：前一根是阴线，当前是阳线，且当前阳线高低点都超过前一根（确保返回Python原生bool类型）
            prev_is_bearish = bool(prev_candle["close"] < prev_candle["open"])
            curr_is_bullish = bool(curr_candle["close"] > curr_candle["open"])
            
            if prev_is_bearish and curr_is_bullish:
                if bool(curr_candle["low"] < prev_candle["low"] and curr_candle["high"] > prev_candle["high"]):
                    reversal_signal = True
                    reversal_pattern = "bullish_engulfing"  # 阳包阴
                    candlestick_patterns["bullish_engulfing"] = True
        
        # 检查锤子线（下影线长，实体小，位于底部）
        if len(last_3) >= 1:
            curr_candle = last_3.iloc[-1]
            body = abs(curr_candle["close"] - curr_candle["open"])
            lower_shadow = min(curr_candle["open"], curr_candle["close"]) - curr_candle["low"]
            upper_shadow = curr_candle["high"] - max(curr_candle["open"], curr_candle["close"])
            total_range = curr_candle["high"] - curr_candle["low"]
            
            if total_range > 0:
                # 锤子线：下影线至少是实体的2倍，上影线很短（确保返回Python原生bool类型）
                if bool(lower_shadow > body * 2 and upper_shadow < body * 0.5):
                    reversal_signal = True
                    reversal_pattern = "hammer"  # 锤子线
                    candlestick_patterns["hammer"] = True
        
        # 检查其他反转形态
        if len(last_3) >= 2:
            # 检查是否连续出现上涨阳线
            bullish_candles = 0
            for i in range(len(last_3)):
                candle = last_3.iloc[i]
                if candle["close"] > candle["open"]:
                    bullish_candles += 1
            
            if bullish_candles >= 2:
                candlestick_patterns["consecutive_bullish"] = True
    
    # 4. 确认上涨阳线是否温和放量
    volume_confirmation = False
    if len(hourly_df) >= 2:
        last_candle = hourly_df.iloc[-1]
        prev_candle = hourly_df.iloc[-2]
        
        # 如果是阳线（确保返回Python原生bool类型）
        if bool(last_candle["close"] > last_candle["open"]):
            # 成交量相比前一根增加，但不过度放量（1.2-2.0倍）
            volume_increase = last_candle["volume"] / prev_candle["volume"] if prev_candle["volume"] > 0 else 1.0
            if 1.2 <= volume_increase <= 2.0:
                volume_confirmation = True
                volume_analysis["volume_confirmation"] = True
                volume_analysis["volume_increase_ratio"] = safe_float(volume_increase)
    
    # 5. 综合判断战术买入点
    tactical_signal = "wait"
    entry_point_detected = False
    confidence = 0
    
    # 只有在日线战略为"做多"时才寻找买入点
    if daily_strategy == "long":
        if pullback_detected and volume_shrinking and reversal_signal:
            # 完美条件：回踩均线 + 成交量萎缩 + 止跌信号
            tactical_signal = "buy"
            entry_point_detected = True
            confidence = min(100, pullback_strength + 20)
        elif pullback_detected and reversal_signal:
            # 良好条件：回踩均线 + 止跌信号
            tactical_signal = "buy"
            entry_point_detected = True
            confidence = min(90, pullback_strength + 10)
        elif pullback_detected and volume_shrinking:
            # 一般条件：回踩均线 + 成交量萎缩
            tactical_signal = "wait"
            entry_point_detected = False
            confidence = 40
        elif reversal_signal and volume_confirmation:
            # 止跌信号 + 温和放量
            tactical_signal = "buy"
            entry_point_detected = True
            confidence = 60
    elif daily_strategy == "short":
        # 做空策略：寻找反弹高点卖出
        if pullback_detected and not volume_shrinking:
            # 反弹但成交量不萎缩 = 可能是假突破
            tactical_signal = "sell"
            entry_point_detected = True
            confidence = 50
        else:
            tactical_signal = "wait"
            entry_point_detected = False
            confidence = 30
    else:
        # 日线为中性，小时线也保持观望
        tactical_signal = "wait"
        entry_point_detected = False
        confidence = 20
    
    return {
        "tactical_signal": tactical_signal,
        "entry_point_detected": entry_point_detected,
        "pullback_analysis": {
            "pullback_detected": pullback_detected,
            "pullback_type": pullback_type,
            "pullback_strength": pullback_strength,
            "near_ma20": near_ma20,
            "near_ma60": near_ma60,
            "distance_to_ma20_pct": safe_float((current_price - current_ma20) / current_ma20 * 100 if current_ma20 > 0 else 0),
            "distance_to_ma60_pct": safe_float((current_price - current_ma60) / current_ma60 * 100 if current_ma60 > 0 else 0),
        },
        "volume_analysis": volume_analysis,
        "candlestick_patterns": {
            **candlestick_patterns,
            "reversal_signal": reversal_signal,
            "reversal_pattern": reversal_pattern,
        },
        "confidence": round(confidence),
        "metrics": {
            "ma_20": safe_float(current_ma20),
            "ma_60": safe_float(current_ma60),
            "current_price": safe_float(current_price),
            "daily_strategy": daily_strategy,
        },
    }

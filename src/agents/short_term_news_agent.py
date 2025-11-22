# 导入 JSON 处理模块，用于序列化和反序列化数据
import json
# 导入 LangChain 的 HumanMessage 类，用于创建人类消息对象
from langchain_core.messages import HumanMessage
# 导入 LangChain 的 ChatPromptTemplate 类，用于创建聊天提示模板
from langchain_core.prompts import ChatPromptTemplate

# 导入 AgentState 类型和 show_agent_reasoning 函数
from src.graph.state import AgentState, show_agent_reasoning
# 导入 Pydantic 的 BaseModel 和 Field，用于数据验证和模型定义
from pydantic import BaseModel, Field
# 导入 Literal 类型，用于定义字面量类型约束
from typing_extensions import Literal
# 导入 LLM 调用函数，用于调用大语言模型
from src.utils.llm import call_llm
# 导入短线新闻分析代理的提示消息生成函数
from src.agents.contexts.short_term_news_agent import get_prompt_messages
# 导入获取美联储降息预期数据的函数
from src.tools.data_api import get_fed_rate_cut_expectation
# 导入新闻管理代理
from src.agents.news_manager import filter_news_for_tickers
# 导入技术分析代理
from src.agents.technicals import technical_analyst_agent
# 导入价格数据获取函数
from src.tools.api import get_prices, prices_to_df
from src.utils.api_key import get_api_key_from_state
from longport.openapi import Period
# 导入持仓信息
from src.mycount import initial_positions, initial_realized_gains, CountInfo


# 定义短线交易决策数据模型
class ShortTermDecision(BaseModel):
    """短线交易决策数据模型"""
    # 交易动作类型：买入、卖出、做空、平仓、持有
    action: Literal["buy", "sell", "short", "cover", "hold"]
    # 交易数量（股数）
    quantity: int = Field(description="Number of shares to trade")
    # 信心度（0-100）
    confidence: int = Field(description="Confidence 0-100")
    # 决策推理说明
    reasoning: str = Field(description="Reasoning for the decision")
    # 建议的交易价格（可选）
    suggested_price: float | None = Field(default=None, description="Suggested buy/sell price per share (optional)")
    # 建议的短线交易时间窗口（默认5天左右）
    time_window: str = Field(default="5个交易日左右", description="Suggested short-term trading time window (around 5 trading days)")
    # 评分信息
    score: dict[str, int] = Field(default_factory=dict, description="Score breakdown")


# 定义短线新闻分析代理输出数据模型
class ShortTermNewsAgentOutput(BaseModel):
    """短线新闻分析代理输出数据模型"""
    # 股票代码到交易决策的字典映射
    decisions: dict[str, ShortTermDecision] = Field(description="Dictionary of ticker to trading decisions")
    # 整体持仓评估
    overall_assessment: str = Field(default="", description="Overall portfolio assessment")


##### 短线新闻分析代理主函数 #####
def short_term_news_agent(state: AgentState, agent_id: str = "short_term_news_agent"):
    """
    分析消息面对当前持仓的影响，并提供短线交易建议
    
    参数:
        state: AgentState 对象，包含数据、消息和元数据
        agent_id: 代理 ID，用于进度跟踪和模型配置
    
    返回:
        更新后的状态，包含新消息和更新后的数据
    """
    # 从 mycount.py 获取持仓信息
    positions = initial_positions
    realized_gains = initial_realized_gains
    
    # 从状态中提取股票代码列表（如果有的话，否则使用持仓中的股票）
    tickers = state["data"].get("tickers", list(positions.keys()))
    
    # 如果没有持仓，返回空决策
    if not positions:
        print("警告: 没有持仓信息")
        return {
            "messages": state["messages"] + [
                HumanMessage(
                    content=json.dumps({"decisions": {}, "overall_assessment": "无持仓信息"}),
                    name=agent_id,
                )
            ],
            "data": state["data"],
        }
    
    # 获取美联储降息预期数据
    fed_expectation = get_fed_rate_cut_expectation()
    print("联储降息预期", fed_expectation)
    state["data"]["fed_rate_cut_expectation"] = fed_expectation
    
    # 使用新闻管理代理筛选相关新闻（会自动更新缓存并使用近半年的新闻）
    # 不使用 progress 跟踪，因为 short_term_news_agent 不需要进度显示
    filtered_news_by_ticker = filter_news_for_tickers(tickers, agent_id, state, days=180, use_progress=False)
    print(f"新闻筛选完成，各股票相关新闻数量: {[(t, len(n)) for t, n in filtered_news_by_ticker.items()]}")
    state["data"]["filtered_news_by_ticker"] = filtered_news_by_ticker
    
    # 调用技术分析代理获取技术面分析结果
    # 确保 state 中有必要的日期信息（如果没有，使用默认值：最近6个月）
    if "start_date" not in state["data"] or "end_date" not in state["data"]:
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        state["data"]["start_date"] = start_date
        state["data"]["end_date"] = end_date
        print(f"使用默认日期范围: {start_date} 至 {end_date}")
    
    # 确保 state 中有 tickers
    state["data"]["tickers"] = tickers
    
    # 确保 state 中有 analyst_signals 字典
    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    
    # 调用技术分析代理获取技术面分析结果
    technical_analysis = {}
    try:
        print("开始技术分析...")
        # 调用技术分析代理
        technical_state = technical_analyst_agent(state, agent_id="technical_analyst_agent")
        # 更新 state 以包含技术分析结果
        state["data"] = technical_state["data"]
        technical_analysis = state["data"].get("analyst_signals", {}).get("technical_analyst_agent", {})
        print(f"技术分析完成，已分析 {len(technical_analysis)} 只股票")
    except Exception as e:
        print(f"⚠️ 技术分析失败: {e}")
        print("将继续使用消息面分析，技术分析数据为空")
        technical_analysis = {}
    
    # 从状态中获取当前价格（如果存在）
    current_prices = state["data"].get("current_prices", {})
    
    # 获取最近价格走势和量价关系分析
    price_trend_analysis = {}
    try:
        print("开始分析最近价格走势和量价关系...")
        api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
        # 获取最近30天的日线数据用于分析
        from datetime import datetime, timedelta
        end_date = state["data"].get("end_date", datetime.now().strftime("%Y-%m-%d"))
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
        
        for ticker in tickers:
            try:
                prices = get_prices(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    period=Period.Day,
                    api_key=api_key,
                )
                if prices and len(prices) >= 5:
                    price_trend_analysis[ticker] = analyze_price_trend_and_volume(prices)
                else:
                    price_trend_analysis[ticker] = {"error": "数据不足"}
            except Exception as e:
                print(f"⚠️  {ticker} 价格走势分析失败: {e}")
                price_trend_analysis[ticker] = {"error": str(e)}
        print(f"价格走势分析完成，已分析 {len([k for k, v in price_trend_analysis.items() if 'error' not in v])} 只股票")
    except Exception as e:
        print(f"⚠️ 价格走势分析失败: {e}")
        price_trend_analysis = {}
    
    # 调用生成交易决策函数
    result = generate_short_term_decision(
        positions=positions,
        realized_gains=realized_gains,
        tickers=tickers,
        current_prices=current_prices,
        fed_expectation=fed_expectation,
        filtered_news_by_ticker=filtered_news_by_ticker,
        technical_analysis=technical_analysis,
        price_trend_analysis=price_trend_analysis,
        agent_id=agent_id,
        state=state,
    )
    
    # 创建 HumanMessage 对象，包含交易决策的 JSON 序列化内容
    message = HumanMessage(
        content=json.dumps({
            "decisions": {ticker: decision.model_dump() for ticker, decision in result.decisions.items()},
            "overall_assessment": result.overall_assessment,
        }, ensure_ascii=False),
        name=agent_id,
    )
    
    # 如果启用了推理显示，则显示代理的推理过程
    if state["metadata"]["show_reasoning"]:
        show_agent_reasoning(
            {ticker: decision.model_dump() for ticker, decision in result.decisions.items()},
            "Short Term News Agent"
        )
    
    # 返回更新后的状态
    return {
        "messages": state["messages"] + [message],
        "data": state["data"],
    }


# 格式化持仓信息，便于模型理解
def format_positions_for_prompt(
    positions: dict,
    realized_gains: dict,
) -> str:
    """
    将持仓信息格式化为易读的字符串
    
    参数:
        positions: 持仓信息字典，格式: {"PYPL": {"long": 60, "long_cost_basis": 67, ...}, ...}
        realized_gains: 已实现盈亏字典，格式: {"PYPL": {"long": -42.6, "short": 0.0}, ...}
    
    返回:
        格式化后的持仓信息字符串
    """
    if not positions:
        return "无持仓 / No positions"
    
    formatted_lines = []
    formatted_lines.append("当前持仓信息 / Current Positions:")
    formatted_lines.append("=" * 60)
    
    for ticker, pos in positions.items():
        long_shares = pos.get("long", 0)
        long_cost = pos.get("long_cost_basis", 0.0)
        short_shares = pos.get("short", 0)
        short_cost = pos.get("short_cost_basis", 0.0)
        
        # 获取已实现盈亏
        realized = realized_gains.get(ticker, {})
        long_realized = realized.get("long", 0.0)
        short_realized = realized.get("short", 0.0)
        
        formatted_lines.append(f"\n【{ticker}】")
        if long_shares > 0:
            formatted_lines.append(f"  多头持仓 / Long Position: {long_shares} 股")
            formatted_lines.append(f"  成本价 / Cost Basis: ${long_cost:.2f}")
            formatted_lines.append(f"  已实现盈亏 / Realized P&L: ${long_realized:.2f}")
        if short_shares > 0:
            formatted_lines.append(f"  空头持仓 / Short Position: {short_shares} 股")
            formatted_lines.append(f"  成本价 / Cost Basis: ${short_cost:.2f}")
            formatted_lines.append(f"  已实现盈亏 / Realized P&L: ${short_realized:.2f}")
        if long_shares == 0 and short_shares == 0:
            formatted_lines.append(f"  无持仓 / No Position")
        formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines)


# 格式化新闻数据，添加中英文对照，便于模型理解
def format_news_for_prompt(filtered_news_by_ticker: dict[str, list[dict]]) -> str:
    """
    将筛选后的新闻格式化为易读的字符串，包含中英文对照
    
    参数:
        filtered_news_by_ticker: 按股票分组的新闻字典，格式: {"PYPL": [新闻列表], "BABA": [新闻列表]}
    
    返回:
        格式化后的新闻字符串，包含中英文对照
    """
    if not filtered_news_by_ticker:
        return "无相关新闻 / No relevant news"
    
    formatted_lines = []
    
    for ticker, news_list in filtered_news_by_ticker.items():
        if not news_list:
            continue
        
        formatted_lines.append(f"\n【{ticker}】相关新闻 / Relevant News for {ticker}:")
        formatted_lines.append("=" * 60)
        
        for idx, news_item in enumerate(news_list, 1):
            title = news_item.get("title", "")
            title_cn = news_item.get("title_cn", "")
            datetime_str = news_item.get("datetime", "")
            labels = news_item.get("labels", [])
            relevance_reason = news_item.get("relevance_reason", "相关新闻")
            
            # 格式化标题（中英文对照）
            if title_cn and title_cn != title:
                title_display = f"{title} / {title_cn}"
            else:
                title_display = title if title else "无标题 / No title"
            
            # 格式化标签
            if labels:
                labels_str = ", ".join(labels)
                labels_display = labels_str
            else:
                labels_display = "无标签 / No labels"
            
            # 格式化时间
            time_display = datetime_str
            
            # 构建新闻条目
            formatted_lines.append(f"\n新闻 {idx} / News {idx}:")
            formatted_lines.append(f"  时间 / Time: {time_display}")
            formatted_lines.append(f"  标签 / Labels: {labels_display}")
            formatted_lines.append(f"  标题 / Title: {title_display}")
            formatted_lines.append(f"  入选理由 / Relevance Reason: {relevance_reason}")
            
            # 添加分隔线
            if idx < len(news_list):
                formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines) if formatted_lines else "无相关新闻 / No relevant news"


# 格式化技术分析结果，便于模型理解
def format_technical_analysis_for_prompt(technical_analysis: dict) -> str:
    """
    将技术分析结果格式化为易读的字符串
    
    参数:
        technical_analysis: 技术分析结果字典，格式: {"TICKER": {signal, confidence, reasoning: {...}}, ...}
    
    返回:
        格式化后的技术分析字符串
    """
    if not technical_analysis:
        return "无技术分析数据 / No technical analysis data"
    
    formatted_lines = []
    formatted_lines.append("技术分析结果 / Technical Analysis Results:")
    formatted_lines.append("=" * 60)
    
    for ticker, analysis in technical_analysis.items():
        signal = analysis.get("signal", "neutral")
        confidence = analysis.get("confidence", 0)
        reasoning = analysis.get("reasoning", {})
        
        formatted_lines.append(f"\n【{ticker}】")
        formatted_lines.append(f"  综合信号 / Overall Signal: {signal}")
        formatted_lines.append(f"  信心度 / Confidence: {confidence}%")
        
        # 格式化各个策略的分析结果
        if reasoning:
            formatted_lines.append(f"  详细分析 / Detailed Analysis:")
            
            # 趋势跟踪
            if "trend_following" in reasoning:
                tf = reasoning["trend_following"]
                formatted_lines.append(f"    - 趋势跟踪 / Trend Following: {tf.get('signal', 'neutral')} (信心度: {tf.get('confidence', 0)}%)")
            
            # 均值回归
            if "mean_reversion" in reasoning:
                mr = reasoning["mean_reversion"]
                formatted_lines.append(f"    - 均值回归 / Mean Reversion: {mr.get('signal', 'neutral')} (信心度: {mr.get('confidence', 0)}%)")
            
            # 动量分析
            if "momentum" in reasoning:
                mom = reasoning["momentum"]
                formatted_lines.append(f"    - 动量分析 / Momentum: {mom.get('signal', 'neutral')} (信心度: {mom.get('confidence', 0)}%)")
            
            # 波动率分析
            if "volatility" in reasoning:
                vol = reasoning["volatility"]
                formatted_lines.append(f"    - 波动率分析 / Volatility: {vol.get('signal', 'neutral')} (信心度: {vol.get('confidence', 0)}%)")
            
            # 统计套利
            if "statistical_arbitrage" in reasoning:
                sa = reasoning["statistical_arbitrage"]
                formatted_lines.append(f"    - 统计套利 / Statistical Arbitrage: {sa.get('signal', 'neutral')} (信心度: {sa.get('confidence', 0)}%)")
            
            # 日线K线分析
            if "daily_kline_analysis" in reasoning:
                daily = reasoning["daily_kline_analysis"]
                strategy = daily.get("strategy", "neutral")
                trend_type = daily.get("trend_type", "unknown")
                trend_strength = daily.get("trend_strength", 0)
                formatted_lines.append(f"    - 日线分析 / Daily K-line: {strategy} (趋势类型: {trend_type}, 强度: {trend_strength})")
            
            # 小时线K线分析
            if "hourly_kline_analysis" in reasoning:
                hourly = reasoning["hourly_kline_analysis"]
                tactical_signal = hourly.get("tactical_signal", "wait")
                entry_point = hourly.get("entry_point_detected", False)
                formatted_lines.append(f"    - 小时线分析 / Hourly K-line: {tactical_signal} (买入点: {'是' if entry_point else '否'})")
        
        formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines)


# 分析最近价格走势和量价关系
def analyze_price_trend_and_volume(prices: list) -> dict:
    """
    分析最近价格走势和量价关系
    
    参数:
        prices: 价格数据列表，每个元素包含 open, close, high, low, volume, time
    
    返回:
        包含价格走势和量价关系分析的字典
    """
    if not prices or len(prices) < 5:
        return {"error": "数据不足"}
    
    # 转换为 DataFrame
    df = prices_to_df(prices)
    if df.empty or len(df) < 5:
        return {"error": "数据不足"}
    
    # 按时间排序（确保最新的数据在最后）
    df = df.sort_index()
    
    # 获取最近的数据
    recent_5d = df.tail(5) if len(df) >= 5 else df
    recent_10d = df.tail(10) if len(df) >= 10 else df
    recent_20d = df.tail(20) if len(df) >= 20 else df
    
    # 计算价格走势
    current_price = float(df["close"].iloc[-1])
    # 计算N天前的价格（如果数据不足，使用最早的数据）
    if len(df) >= 5:
        price_5d_ago = float(df["close"].iloc[-5])
    else:
        price_5d_ago = float(df["close"].iloc[0]) if len(df) > 0 else current_price
    
    if len(df) >= 10:
        price_10d_ago = float(df["close"].iloc[-10])
    else:
        price_10d_ago = float(df["close"].iloc[0]) if len(df) > 0 else current_price
    
    if len(df) >= 20:
        price_20d_ago = float(df["close"].iloc[-20])
    else:
        price_20d_ago = float(df["close"].iloc[0]) if len(df) > 0 else current_price
    
    # 计算涨跌幅
    change_5d = ((current_price - price_5d_ago) / price_5d_ago * 100) if price_5d_ago > 0 else 0
    change_10d = ((current_price - price_10d_ago) / price_10d_ago * 100) if price_10d_ago > 0 else 0
    change_20d = ((current_price - price_20d_ago) / price_20d_ago * 100) if price_20d_ago > 0 else 0
    
    # 计算最近5天的价格波动
    high_5d = float(recent_5d["high"].max())
    low_5d = float(recent_5d["low"].min())
    volatility_5d = ((high_5d - low_5d) / current_price * 100) if current_price > 0 else 0
    
    # 分析量价关系
    # 计算最近5天的量价关系
    price_changes = recent_5d["close"].pct_change().dropna()
    volume_changes = recent_5d["volume"].pct_change().dropna()
    
    # 对齐数据
    min_len = min(len(price_changes), len(volume_changes))
    if min_len > 1:
        price_changes_aligned = price_changes.tail(min_len)
        volume_changes_aligned = volume_changes.tail(min_len)
        
        # 计算量价相关性
        correlation = float(price_changes_aligned.corr(volume_changes_aligned)) if len(price_changes_aligned) > 1 else 0.0
        
        # 统计价涨量增、价跌量缩的情况
        price_up_volume_up = 0
        price_down_volume_down = 0
        price_up_volume_down = 0  # 量价背离
        price_down_volume_up = 0  # 量价背离
        
        for i in range(1, len(recent_5d)):
            price_up = recent_5d["close"].iloc[i] > recent_5d["close"].iloc[i-1]
            volume_up = recent_5d["volume"].iloc[i] > recent_5d["volume"].iloc[i-1]
            
            if price_up and volume_up:
                price_up_volume_up += 1
            elif not price_up and not volume_up:
                price_down_volume_down += 1
            elif price_up and not volume_up:
                price_up_volume_down += 1
            elif not price_up and volume_up:
                price_down_volume_up += 1
    else:
        correlation = 0.0
        price_up_volume_up = 0
        price_down_volume_down = 0
        price_up_volume_down = 0
        price_down_volume_up = 0
    
    # 计算平均成交量
    avg_volume_5d = float(recent_5d["volume"].mean())
    avg_volume_20d = float(recent_20d["volume"].mean()) if len(recent_20d) >= 5 else avg_volume_5d
    volume_ratio = (avg_volume_5d / avg_volume_20d) if avg_volume_20d > 0 else 1.0
    
    # 判断量价关系类型
    if correlation > 0.3:
        volume_price_relation = "健康 / Healthy (价涨量增、价跌量缩)"
    elif correlation < -0.3:
        volume_price_relation = "背离 / Divergence (价涨量缩或价跌量增)"
    else:
        volume_price_relation = "弱相关 / Weak correlation"
    
    # 判断价格趋势
    if change_5d > 2:
        trend_5d = "强势上涨 / Strong uptrend"
    elif change_5d > 0:
        trend_5d = "温和上涨 / Mild uptrend"
    elif change_5d > -2:
        trend_5d = "震荡 / Sideways"
    else:
        trend_5d = "下跌 / Downtrend"
    
    return {
        "current_price": round(current_price, 2),
        "price_changes": {
            "5d": round(change_5d, 2),
            "10d": round(change_10d, 2),
            "20d": round(change_20d, 2),
        },
        "volatility_5d": round(volatility_5d, 2),
        "trend_5d": trend_5d,
        "volume_price_relation": volume_price_relation,
        "volume_price_correlation": round(correlation, 3),
        "volume_price_stats": {
            "price_up_volume_up": price_up_volume_up,
            "price_down_volume_down": price_down_volume_down,
            "price_up_volume_down": price_up_volume_down,
            "price_down_volume_up": price_down_volume_up,
        },
        "volume_analysis": {
            "avg_volume_5d": int(avg_volume_5d),
            "avg_volume_20d": int(avg_volume_20d),
            "volume_ratio": round(volume_ratio, 2),
        },
    }


# 格式化价格走势和量价关系分析，便于模型理解
def format_price_trend_analysis_for_prompt(price_trend_analysis: dict) -> str:
    """
    将价格走势和量价关系分析格式化为易读的字符串
    
    参数:
        price_trend_analysis: 价格走势分析字典，格式: {"TICKER": {分析结果}, ...}
    
    返回:
        格式化后的价格走势分析字符串
    """
    if not price_trend_analysis:
        return "无价格走势数据 / No price trend data"
    
    formatted_lines = []
    formatted_lines.append("最近价格走势和量价关系分析 / Recent Price Trend and Volume-Price Relationship Analysis:")
    formatted_lines.append("=" * 60)
    
    for ticker, analysis in price_trend_analysis.items():
        if "error" in analysis:
            formatted_lines.append(f"\n【{ticker}】")
            formatted_lines.append(f"  分析失败 / Analysis Failed: {analysis['error']}")
            formatted_lines.append("-" * 60)
            continue
        
        formatted_lines.append(f"\n【{ticker}】")
        formatted_lines.append(f"  当前价格 / Current Price: ${analysis.get('current_price', 0):.2f}")
        
        # 价格走势
        price_changes = analysis.get("price_changes", {})
        formatted_lines.append(f"  价格走势 / Price Trend:")
        formatted_lines.append(f"    - 5日涨跌幅 / 5-day Change: {price_changes.get('5d', 0):+.2f}%")
        formatted_lines.append(f"    - 10日涨跌幅 / 10-day Change: {price_changes.get('10d', 0):+.2f}%")
        formatted_lines.append(f"    - 20日涨跌幅 / 20-day Change: {price_changes.get('20d', 0):+.2f}%")
        formatted_lines.append(f"    - 5日趋势 / 5-day Trend: {analysis.get('trend_5d', 'unknown')}")
        formatted_lines.append(f"    - 5日波动率 / 5-day Volatility: {analysis.get('volatility_5d', 0):.2f}%")
        
        # 量价关系
        formatted_lines.append(f"  量价关系 / Volume-Price Relationship:")
        formatted_lines.append(f"    - 关系类型 / Relation Type: {analysis.get('volume_price_relation', 'unknown')}")
        formatted_lines.append(f"    - 相关性 / Correlation: {analysis.get('volume_price_correlation', 0):.3f}")
        
        volume_price_stats = analysis.get("volume_price_stats", {})
        formatted_lines.append(f"    - 价涨量增天数 / Price Up Volume Up Days: {volume_price_stats.get('price_up_volume_up', 0)}")
        formatted_lines.append(f"    - 价跌量缩天数 / Price Down Volume Down Days: {volume_price_stats.get('price_down_volume_down', 0)}")
        formatted_lines.append(f"    - 价涨量缩天数 / Price Up Volume Down Days (背离): {volume_price_stats.get('price_up_volume_down', 0)}")
        formatted_lines.append(f"    - 价跌量增天数 / Price Down Volume Up Days (背离): {volume_price_stats.get('price_down_volume_up', 0)}")
        
        # 成交量分析
        volume_analysis = analysis.get("volume_analysis", {})
        formatted_lines.append(f"  成交量分析 / Volume Analysis:")
        formatted_lines.append(f"    - 5日平均成交量 / 5-day Avg Volume: {volume_analysis.get('avg_volume_5d', 0):,}")
        formatted_lines.append(f"    - 20日平均成交量 / 20-day Avg Volume: {volume_analysis.get('avg_volume_20d', 0):,}")
        formatted_lines.append(f"    - 成交量比率 / Volume Ratio (5d/20d): {volume_analysis.get('volume_ratio', 1.0):.2f}")
        if volume_analysis.get("volume_ratio", 1.0) > 1.2:
            formatted_lines.append(f"      → 近期成交量放大 / Recent volume increase")
        elif volume_analysis.get("volume_ratio", 1.0) < 0.8:
            formatted_lines.append(f"      → 近期成交量萎缩 / Recent volume decrease")
        
        formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines)


# 从 LLM 获取短线交易决策
def generate_short_term_decision(
    positions: dict,
    realized_gains: dict,
    tickers: list[str],
    current_prices: dict[str, float],
    fed_expectation: dict[str, float] | None,
    filtered_news_by_ticker: dict[str, list[dict]],
    technical_analysis: dict,
    price_trend_analysis: dict,
    agent_id: str,
    state: AgentState,
) -> ShortTermNewsAgentOutput:
    """
    使用 LLM 生成短线交易决策
    
    参数:
        positions: 持仓信息字典
        realized_gains: 已实现盈亏字典
        tickers: 股票代码列表
        current_prices: 当前价格字典
        fed_expectation: 美联储降息预期数据
        filtered_news_by_ticker: 筛选后的新闻（按股票分组）
        technical_analysis: 技术分析结果字典
        price_trend_analysis: 价格走势和量价关系分析字典
        agent_id: 代理 ID
        state: AgentState 对象
    
    返回:
        ShortTermNewsAgentOutput 对象，包含交易决策
    """
    # 格式化持仓信息
    positions_str = format_positions_for_prompt(positions, realized_gains)
    
    # 格式化新闻信息
    formatted_news = format_news_for_prompt(filtered_news_by_ticker)
    
    # 格式化技术分析信息
    formatted_technical = format_technical_analysis_for_prompt(technical_analysis)
    
    # 格式化价格走势和量价关系分析信息
    formatted_price_trend = format_price_trend_analysis_for_prompt(price_trend_analysis)
    
    # 构建给大模型的提示模板
    template = ChatPromptTemplate.from_messages(get_prompt_messages())
    
    # 构建提示数据
    prompt_data = {
        "positions": positions_str,
        "current_prices": json.dumps(current_prices, separators=(",", ":"), ensure_ascii=False),
    }
    
    # 如果存在降息预期数据，添加到提示数据中
    if fed_expectation:
        prompt_data["fed_expectation"] = json.dumps(fed_expectation, separators=(",", ":"), ensure_ascii=False)
    else:
        prompt_data["fed_expectation"] = "null"
    
    # 如果存在筛选后的新闻，添加到提示数据中
    if formatted_news:
        prompt_data["latest_news"] = formatted_news
    else:
        prompt_data["latest_news"] = "无相关新闻 / No relevant news"
    
    # 如果存在技术分析数据，添加到提示数据中
    if formatted_technical:
        prompt_data["technical_analysis"] = formatted_technical
    else:
        prompt_data["technical_analysis"] = "无技术分析数据 / No technical analysis data"
    
    # 如果存在价格走势分析数据，添加到提示数据中
    if formatted_price_trend:
        prompt_data["price_trend_analysis"] = formatted_price_trend
    else:
        prompt_data["price_trend_analysis"] = "无价格走势数据 / No price trend data"
    
    # 调用模板生成提示
    prompt = template.invoke(prompt_data)
    
    # 调试输出
    print("短线新闻分析 >", "持仓数量:", len(positions), "股票数量:", len(tickers))
    print("*" * 100)
    
    # 用于存储LLM调用时的错误信息
    llm_error_info = {"error": None, "failed": False}
    
    # 默认工厂函数：如果 LLM 失败，则将所有股票填充为持有
    def create_default_output():
        llm_error_info["failed"] = True
        error_msg = llm_error_info.get("error", "LLM调用失败（重试3次后仍失败）")
        decisions = {}
        for ticker in tickers:
            decisions[ticker] = ShortTermDecision(
                action="hold",
                quantity=0,
                confidence=0,
                reasoning=f"LLM调用失败，使用默认决策：持有。失败原因: {error_msg}",
                suggested_price=None,
                time_window="5个交易日左右",
                score={},
            )
        return ShortTermNewsAgentOutput(
            decisions=decisions,
            overall_assessment=f"无法生成分析，使用默认持有决策。LLM调用失败原因: {error_msg}",
        )
    
    # 调用 LLM 生成交易决策
    # 注意：call_llm内部已经处理了重试逻辑，如果失败会调用default_factory
    llm_out = call_llm(
        prompt=prompt,
        pydantic_model=ShortTermNewsAgentOutput,
        agent_name=agent_id,
        state=state,
        default_factory=create_default_output,
    )
    
    # 检查是否使用了默认输出（通过检查是否设置了failed标志）
    if llm_error_info.get("failed", False):
        error_msg = llm_error_info.get("error") or "LLM调用失败（重试3次后仍失败，请查看上方错误信息）"
        print(f"\n⚠️ LLM调用失败，已使用默认持有决策")
        print(f"失败原因: {error_msg}")
        print("所有股票的决策已设置为默认的'持有'操作，信心度为0")
    
    # 保存 LLM 的完整分析内容到状态中，供展示使用
    llm_analysis_content = {}
    for ticker, decision in llm_out.decisions.items():
        llm_analysis_content[ticker] = {
            "action": decision.action,
            "quantity": decision.quantity,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,
            "suggested_price": decision.suggested_price,
            "time_window": decision.time_window,
            "score": decision.score,
        }
    
    state["data"]["short_term_news_analysis"] = llm_analysis_content
    state["data"]["short_term_overall_assessment"] = llm_out.overall_assessment
    
    return llm_out


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
# 导入日期时间处理
from datetime import datetime, timedelta


def filter_news_by_hours(filtered_news_by_ticker: dict[str, list[dict]], hours: int = 2) -> dict[str, list[dict]]:
    """
    过滤出近N小时内的新闻（用于防止重复发送旧新闻）
    
    参数:
        filtered_news_by_ticker: 按股票分组的新闻字典，格式: {"TICKER": [新闻列表], ...}
        hours: 要保留的小时数，默认2小时
    
    返回:
        近N小时内的新闻字典
    """
    if not filtered_news_by_ticker:
        return {}
    
    # 计算截止时间
    cutoff_time = datetime.now() - timedelta(hours=hours)
    
    result = {}
    for ticker, news_list in filtered_news_by_ticker.items():
        if not news_list:
            result[ticker] = []
            continue
        
        recent_news = []
        for news_item in news_list:
            try:
                # 解析新闻日期时间
                news_datetime_str = news_item.get("datetime", "")
                if not news_datetime_str:
                    continue
                
                # 解析日期时间字符串，格式: "2025-11-19 15:38"
                news_datetime = datetime.strptime(news_datetime_str, "%Y-%m-%d %H:%M")
                
                # 如果新闻日期在截止时间之后，则包含
                if news_datetime >= cutoff_time:
                    recent_news.append(news_item)
            except Exception as e:
                # 如果解析失败，跳过该新闻
                print(f"⚠️ 解析新闻时间失败: {news_datetime_str}, 错误: {e}")
                continue
        
        result[ticker] = recent_news
    
    return result


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
    
    # 使用新闻管理代理筛选相关新闻（只使用近5天的新闻）
    # 不使用 progress 跟踪，因为 short_term_news_agent 不需要进度显示
    filtered_news_by_ticker = filter_news_for_tickers(tickers, agent_id, state, days=5, use_progress=False)
    print(f"新闻筛选完成（5天内），各股票相关新闻数量: {[(t, len(n)) for t, n in filtered_news_by_ticker.items()]}")
    
    # 再次过滤，只保留近2小时内的新闻（防止重复发送旧新闻）
    filtered_news_by_ticker = filter_news_by_hours(filtered_news_by_ticker, hours=2)
    print(f"新闻筛选完成（2小时内），各股票相关新闻数量: {[(t, len(n)) for t, n in filtered_news_by_ticker.items()]}")
    state["data"]["filtered_news_by_ticker"] = filtered_news_by_ticker
    
    # 调用技术分析代理获取技术面分析结果
    # 确保 state 中有必要的日期信息（如果没有，使用默认值：最近6个月）
    if "start_date" not in state["data"] or "end_date" not in state["data"]:
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
    
    # 获取最近价格走势和量价关系分析（使用2小时K线）
    price_trend_analysis = {}
    try:
        print("开始分析最近价格走势和量价关系（2小时K线）...")
        api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
        # 获取最近5天的2小时K线数据用于分析
        end_date = state["data"].get("end_date", datetime.now().strftime("%Y-%m-%d"))
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        
        for ticker in tickers:
            try:
                prices = get_prices(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                    period=Period.Min_120,  # 使用2小时K线
                    api_key=api_key,
                )
                if prices and len(prices) >= 5:
                    price_trend_analysis[ticker] = analyze_price_trend_and_volume(prices)
                else:
                    price_trend_analysis[ticker] = {"error": "数据不足"}
            except Exception as e:
                print(f"⚠️  {ticker} 价格走势分析失败: {e}")
                price_trend_analysis[ticker] = {"error": str(e)}
        print(f"价格走势分析完成（2小时K线），已分析 {len([k for k, v in price_trend_analysis.items() if 'error' not in v])} 只股票")
    except Exception as e:
        print(f"⚠️ 价格走势分析失败: {e}")
        price_trend_analysis = {}
    
    # 加载近5天的历史操作记录作为参考
    from src.tools.alert_utils import load_recent_operations_history
    recent_operations = load_recent_operations_history(days=5)
    state["data"]["recent_operations"] = recent_operations
    
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
        recent_operations=recent_operations,
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
    
    # ==================== 量价关系分析 ====================
    # 量价关系是技术分析中的重要指标，用于判断市场情绪和趋势的可靠性
    # 健康的量价关系：价涨量增（上涨有资金支持）、价跌量缩（下跌缺乏抛压）
    # 背离的量价关系：价涨量缩（上涨乏力）、价跌量增（下跌有大量抛压）
    
    # 【步骤1】计算价格和成交量的变化率
    # 使用 pct_change() 计算相邻K线之间的百分比变化
    # 例如：如果第1根K线收盘价是100，第2根是105，则变化率是5%
    price_changes = recent_5d["close"].pct_change().dropna()  # 价格变化率序列，去掉NaN
    volume_changes = recent_5d["volume"].pct_change().dropna()  # 成交量变化率序列，去掉NaN
    
    # 【步骤2】对齐价格变化和成交量变化的数据
    # 由于 pct_change() 会产生NaN（第一行没有前一行可比较），需要确保两个序列长度一致
    min_len = min(len(price_changes), len(volume_changes))
    if min_len > 1:
        # 取对齐后的数据（从尾部取，确保是最新的数据）
        price_changes_aligned = price_changes.tail(min_len)
        volume_changes_aligned = volume_changes.tail(min_len)
        
        # 【步骤3】计算量价相关性（皮尔逊相关系数）
        # 相关系数范围：-1 到 +1
        #   +1：完全正相关（价涨量增、价跌量缩，健康关系）
        #   -1：完全负相关（价涨量缩、价跌量增，背离关系）
        #    0：无相关性（量价关系不明确）
        # 使用 pandas 的 corr() 方法计算皮尔逊相关系数
        correlation = float(price_changes_aligned.corr(volume_changes_aligned)) if len(price_changes_aligned) > 1 else 0.0
        
        # 【步骤4】逐K线统计量价关系的四种情况
        # 遍历最近5天的每一根K线，与前一根K线比较，统计量价关系
        price_up_volume_up = 0      # 价涨量增：价格上涨且成交量增加（健康上涨信号）
        price_down_volume_down = 0  # 价跌量缩：价格下跌且成交量减少（健康下跌信号，抛压不重）
        price_up_volume_down = 0    # 价涨量缩：价格上涨但成交量减少（背离，上涨乏力，可能见顶）
        price_down_volume_up = 0    # 价跌量增：价格下跌但成交量增加（背离，大量抛压，可能加速下跌）
        
        # 从第2根K线开始遍历（第1根没有前一根可比较）
        for i in range(1, len(recent_5d)):
            # 判断当前K线相比前一根K线的价格和成交量变化
            price_up = recent_5d["close"].iloc[i] > recent_5d["close"].iloc[i-1]  # 价格是否上涨
            volume_up = recent_5d["volume"].iloc[i] > recent_5d["volume"].iloc[i-1]  # 成交量是否增加
            
            # 根据价格和成交量的变化组合，统计对应的量价关系类型
            if price_up and volume_up:
                # 价涨量增：健康的上涨信号，有资金推动
                price_up_volume_up += 1
            elif not price_up and not volume_up:
                # 价跌量缩：健康的下跌信号，抛压不重，可能是正常回调
                price_down_volume_down += 1
            elif price_up and not volume_up:
                # 价涨量缩：背离信号，上涨缺乏成交量支持，可能上涨乏力或见顶
                price_up_volume_down += 1
            elif not price_up and volume_up:
                # 价跌量增：背离信号，下跌伴随大量抛压，可能加速下跌
                price_down_volume_up += 1
    else:
        # 数据不足，无法计算量价关系，使用默认值
        correlation = 0.0
        price_up_volume_up = 0
        price_down_volume_down = 0
        price_up_volume_down = 0
        price_down_volume_up = 0
    
    # 【步骤5】计算成交量分析指标
    # 通过比较短期和长期平均成交量，判断近期成交量的活跃程度
    avg_volume_5d = float(recent_5d["volume"].mean())  # 最近5根K线的平均成交量
    avg_volume_20d = float(recent_20d["volume"].mean()) if len(recent_20d) >= 5 else avg_volume_5d  # 最近20根K线的平均成交量
    # 成交量比率：短期成交量 / 长期成交量
    #   > 1.2：近期成交量放大，市场活跃度提升
    #   < 0.8：近期成交量萎缩，市场活跃度下降
    #   ≈ 1.0：成交量保持稳定
    volume_ratio = (avg_volume_5d / avg_volume_20d) if avg_volume_20d > 0 else 1.0
    
    # 【步骤5.5】放量检测与分析
    # 放量定义：当日成交量比上一交易日放大10%以上，或连续多日成交量持续增加
    # 放量后大概率会涨的三种情况：底部放量、突破压力位时放量、上涨初期持续放量
    volume_surge_analysis = {}
    
    if len(recent_5d) >= 2:
        # 获取最近几根K线的数据
        latest_volume = float(recent_5d["volume"].iloc[-1])  # 最新一根K线的成交量
        prev_volume = float(recent_5d["volume"].iloc[-2])  # 前一根K线的成交量
        
        # 检测单日放量：当日成交量比上一交易日放大10%以上
        volume_surge_single_day = False
        volume_surge_ratio = 0.0
        if prev_volume > 0:
            volume_surge_ratio = ((latest_volume - prev_volume) / prev_volume * 100) if prev_volume > 0 else 0.0
            volume_surge_single_day = volume_surge_ratio >= 10.0  # 放大10%以上视为放量
        
        # 检测连续多日成交量持续增加
        volume_surge_continuous = False
        continuous_days = 0
        if len(recent_5d) >= 3:
            # 检查最近3根K线是否连续放量
            volumes = recent_5d["volume"].tail(3).values
            if len(volumes) >= 3:
                # 检查是否连续递增
                if volumes[2] > volumes[1] > volumes[0]:
                    volume_surge_continuous = True
                    continuous_days = 3
                elif volumes[2] > volumes[1]:
                    continuous_days = 2
        
        # 判断是否放量
        is_volume_surge = volume_surge_single_day or volume_surge_continuous
        
        if is_volume_surge:
            # 计算价格位置（用于判断底部放量）
            # 获取更长期的价格数据来判断是否在底部
            if len(df) >= 20:
                price_20d_ago = float(df["close"].iloc[-20])
                price_10d_ago = float(df["close"].iloc[-10]) if len(df) >= 10 else current_price
                price_5d_ago = float(df["close"].iloc[-5]) if len(df) >= 5 else current_price
                
                # 判断是否在底部：最近20日、10日、5日都是下跌或震荡，且当前价格接近近期低点
                price_decline_20d = ((current_price - price_20d_ago) / price_20d_ago * 100) if price_20d_ago > 0 else 0
                price_decline_10d = ((current_price - price_10d_ago) / price_10d_ago * 100) if price_10d_ago > 0 else 0
                price_decline_5d = ((current_price - price_5d_ago) / price_5d_ago * 100) if price_5d_ago > 0 else 0
                
                # 计算近期最低价
                recent_low = float(recent_5d["low"].min())
                recent_high = float(recent_5d["high"].max())
                price_position = ((current_price - recent_low) / (recent_high - recent_low)) if (recent_high - recent_low) > 0 else 0.5
                
                # 判断底部放量：长期下跌后，价格在低位（价格位置<0.3），且出现放量
                is_bottom_surge = (
                    price_decline_20d < -5 and  # 20日跌幅超过5%
                    price_decline_10d <= 0 and  # 10日不涨或下跌
                    price_position < 0.3 and  # 价格在近期低位的30%范围内
                    is_volume_surge
                )
                
                # 判断突破压力位时放量：价格上涨突破近期高点，且放量
                # 这里简化处理：如果当前价格接近或突破近期高点，且放量
                is_breakthrough_surge = (
                    current_price >= recent_high * 0.98 and  # 价格接近或突破近期高点（98%以上）
                    change_5d > 0 and  # 5日上涨
                    is_volume_surge
                )
                
                # 判断上涨初期持续放量：上涨初期（5日涨幅>0但<5%），且连续多日放量
                is_early_uptrend_surge = (
                    0 < change_5d < 5 and  # 5日涨幅在0-5%之间（上涨初期）
                    volume_surge_continuous and  # 连续多日放量
                    price_up_volume_up >= 2  # 价涨量增的天数>=2
                )
                
                # 综合判断放量类型和看涨概率
                surge_type = []
                bullish_probability = 0
                
                if is_bottom_surge:
                    surge_type.append("底部放量")
                    bullish_probability = max(bullish_probability, 70)  # 底部放量看涨概率较高
                
                if is_breakthrough_surge:
                    surge_type.append("突破压力位放量")
                    bullish_probability = max(bullish_probability, 75)  # 突破放量看涨概率很高
                
                if is_early_uptrend_surge:
                    surge_type.append("上涨初期持续放量")
                    bullish_probability = max(bullish_probability, 65)  # 上涨初期放量看涨概率较高
                
                # 如果检测到放量但无法归类，标记为"一般放量"
                if not surge_type:
                    surge_type.append("一般放量")
                    bullish_probability = 50  # 一般放量看涨概率中等
                
                volume_surge_analysis = {
                    "is_volume_surge": True,
                    "surge_type": surge_type,
                    "surge_ratio": round(volume_surge_ratio, 2) if volume_surge_single_day else 0.0,
                    "continuous_days": continuous_days,
                    "bullish_probability": bullish_probability,
                    "price_position": round(price_position, 2) if len(df) >= 20 else None,
                    "is_bottom_surge": is_bottom_surge,
                    "is_breakthrough_surge": is_breakthrough_surge,
                    "is_early_uptrend_surge": is_early_uptrend_surge,
                }
            else:
                # 数据不足，无法判断放量类型
                volume_surge_analysis = {
                    "is_volume_surge": True,
                    "surge_type": ["一般放量"],
                    "surge_ratio": round(volume_surge_ratio, 2) if volume_surge_single_day else 0.0,
                    "continuous_days": continuous_days,
                    "bullish_probability": 50,
                    "price_position": None,
                    "is_bottom_surge": False,
                    "is_breakthrough_surge": False,
                    "is_early_uptrend_surge": False,
                }
        else:
            # 未检测到放量
            volume_surge_analysis = {
                "is_volume_surge": False,
                "surge_type": [],
                "surge_ratio": 0.0,
                "continuous_days": 0,
                "bullish_probability": 0,
                "price_position": None,
                "is_bottom_surge": False,
                "is_breakthrough_surge": False,
                "is_early_uptrend_surge": False,
            }
    else:
        # 数据不足，无法检测放量
        volume_surge_analysis = {
            "is_volume_surge": False,
            "surge_type": [],
            "surge_ratio": 0.0,
            "continuous_days": 0,
            "bullish_probability": 0,
            "price_position": None,
            "is_bottom_surge": False,
            "is_breakthrough_surge": False,
            "is_early_uptrend_surge": False,
        }
    
    # 【步骤6】根据相关系数判断量价关系类型
    # 这是对量价关系的综合判断，用于快速识别市场状态
    if correlation > 0.3:
        # 相关系数 > 0.3：正相关较强，量价关系健康
        # 说明价格上涨时成交量增加，价格下跌时成交量减少，这是健康的量价关系
        volume_price_relation = "健康 / Healthy (价涨量增、价跌量缩)"
    elif correlation < -0.3:
        # 相关系数 < -0.3：负相关较强，量价关系背离
        # 说明价格上涨时成交量减少，或价格下跌时成交量增加，这是背离的量价关系
        # 背离通常意味着趋势可能反转或失去动力
        volume_price_relation = "背离 / Divergence (价涨量缩或价跌量增)"
    else:
        # 相关系数在 -0.3 到 0.3 之间：相关性较弱
        # 量价关系不明确，需要结合其他指标判断
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
        "volume_surge_analysis": volume_surge_analysis,  # 放量分析结果
    }


# 格式化历史操作记录，便于模型理解
def format_recent_operations_for_prompt(recent_operations: dict) -> str:
    """
    将近5天的历史操作记录格式化为易读的字符串
    
    参数:
        recent_operations: 历史操作字典，格式: {"TICKER": [{"timestamp": "...", "action": "...", "quantity": ..., "confidence": ..., ...}, ...], ...}
    
    返回:
        格式化后的历史操作字符串
    """
    if not recent_operations:
        return "无历史操作记录 / No recent operations history"
    
    formatted_lines = []
    formatted_lines.append("近5天的历史操作记录 / Recent Operations History (Last 5 Days):")
    formatted_lines.append("=" * 60)
    
    for ticker, operations in recent_operations.items():
        if not operations:
            continue
        
        formatted_lines.append(f"\n【{ticker}】")
        for idx, op in enumerate(operations, 1):
            timestamp = op.get("timestamp", "")
            action = op.get("action", "hold")
            quantity = op.get("quantity", 0)
            confidence = op.get("confidence", 0)
            reasoning = op.get("reasoning", "")
            suggested_price = op.get("suggested_price")
            
            action_emoji = {
                "buy": "📈",
                "sell": "📉",
                "short": "🔻",
                "cover": "🔺",
                "hold": "⏸️"
            }.get(action, "⏸️")
            
            action_desc = format_action_description_for_operations(action, quantity)
            formatted_lines.append(f"\n  操作 {idx} / Operation {idx}:")
            formatted_lines.append(f"    时间 / Time: {timestamp}")
            formatted_lines.append(f"    操作 / Action: {action_emoji} {action_desc}")
            formatted_lines.append(f"    信心度 / Confidence: {confidence}%")
            if suggested_price:
                formatted_lines.append(f"    建议价格 / Suggested Price: ${suggested_price:.2f}")
            if reasoning:
                reasoning_short = reasoning[:150] + "..." if len(reasoning) > 150 else reasoning
                formatted_lines.append(f"    原因 / Reasoning: {reasoning_short}")
        
        formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines) if formatted_lines else "无历史操作记录 / No recent operations history"


# 辅助函数：格式化操作描述（用于历史操作显示）
def format_action_description_for_operations(action: str, quantity: int) -> str:
    """格式化操作描述，用于历史操作显示"""
    if action == "buy" and quantity > 0:
        return f"买入 {quantity}股"
    elif action == "sell" and quantity > 0:
        return f"卖出 {quantity}股"
    elif action == "short" and quantity > 0:
        return f"做空 {quantity}股"
    elif action == "cover" and quantity > 0:
        return f"平仓 {quantity}股"
    else:
        return "持有"


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
    formatted_lines.append("最近价格走势和量价关系分析（2小时K线）/ Recent Price Trend and Volume-Price Relationship Analysis (2-hour K-line):")
    formatted_lines.append("=" * 60)
    
    for ticker, analysis in price_trend_analysis.items():
        if "error" in analysis:
            formatted_lines.append(f"\n【{ticker}】")
            formatted_lines.append(f"  分析失败 / Analysis Failed: {analysis['error']}")
            formatted_lines.append("-" * 60)
            continue
        
        formatted_lines.append(f"\n【{ticker}】")
        formatted_lines.append(f"  当前价格 / Current Price: ${analysis.get('current_price', 0):.2f}")
        
        # 价格走势（基于2小时K线，5根K线约10小时，10根K线约20小时，20根K线约40小时）
        price_changes = analysis.get("price_changes", {})
        formatted_lines.append(f"  价格走势 / Price Trend (基于2小时K线 / Based on 2-hour K-line):")
        formatted_lines.append(f"    - 最近5根K线涨跌幅 / Last 5 K-lines Change (~10 hours): {price_changes.get('5d', 0):+.2f}%")
        formatted_lines.append(f"    - 最近10根K线涨跌幅 / Last 10 K-lines Change (~20 hours): {price_changes.get('10d', 0):+.2f}%")
        formatted_lines.append(f"    - 最近20根K线涨跌幅 / Last 20 K-lines Change (~40 hours): {price_changes.get('20d', 0):+.2f}%")
        formatted_lines.append(f"    - 最近5根K线趋势 / Last 5 K-lines Trend: {analysis.get('trend_5d', 'unknown')}")
        formatted_lines.append(f"    - 最近5根K线波动率 / Last 5 K-lines Volatility: {analysis.get('volatility_5d', 0):.2f}%")
        
        # 量价关系
        formatted_lines.append(f"  量价关系 / Volume-Price Relationship:")
        formatted_lines.append(f"    - 关系类型 / Relation Type: {analysis.get('volume_price_relation', 'unknown')}")
        formatted_lines.append(f"    - 相关性 / Correlation: {analysis.get('volume_price_correlation', 0):.3f}")
        
        volume_price_stats = analysis.get("volume_price_stats", {})
        formatted_lines.append(f"    - 价涨量增天数 / Price Up Volume Up Days: {volume_price_stats.get('price_up_volume_up', 0)}")
        formatted_lines.append(f"    - 价跌量缩天数 / Price Down Volume Down Days: {volume_price_stats.get('price_down_volume_down', 0)}")
        formatted_lines.append(f"    - 价涨量缩天数 / Price Up Volume Down Days (背离): {volume_price_stats.get('price_up_volume_down', 0)}")
        formatted_lines.append(f"    - 价跌量增天数 / Price Down Volume Up Days (背离): {volume_price_stats.get('price_down_volume_up', 0)}")
        
        # 成交量分析（基于2小时K线）
        volume_analysis = analysis.get("volume_analysis", {})
        formatted_lines.append(f"  成交量分析 / Volume Analysis (基于2小时K线 / Based on 2-hour K-line):")
        formatted_lines.append(f"    - 最近5根K线平均成交量 / Last 5 K-lines Avg Volume: {volume_analysis.get('avg_volume_5d', 0):,}")
        formatted_lines.append(f"    - 最近20根K线平均成交量 / Last 20 K-lines Avg Volume: {volume_analysis.get('avg_volume_20d', 0):,}")
        formatted_lines.append(f"    - 成交量比率 / Volume Ratio (5 K-lines / 20 K-lines): {volume_analysis.get('volume_ratio', 1.0):.2f}")
        if volume_analysis.get("volume_ratio", 1.0) > 1.2:
            formatted_lines.append(f"      → 近期成交量放大 / Recent volume increase")
        elif volume_analysis.get("volume_ratio", 1.0) < 0.8:
            formatted_lines.append(f"      → 近期成交量萎缩 / Recent volume decrease")
        
        # 放量分析（重要信号）
        volume_surge = analysis.get("volume_surge_analysis", {})
        if volume_surge.get("is_volume_surge", False):
            formatted_lines.append(f"  放量分析 / Volume Surge Analysis (重要信号 / Important Signal):")
            surge_types = volume_surge.get("surge_type", [])
            if surge_types:
                formatted_lines.append(f"    - 放量类型 / Surge Type: {', '.join(surge_types)}")
            
            surge_ratio = volume_surge.get("surge_ratio", 0.0)
            if surge_ratio > 0:
                formatted_lines.append(f"    - 单日放量幅度 / Single Day Surge Ratio: {surge_ratio:.2f}%")
            
            continuous_days = volume_surge.get("continuous_days", 0)
            if continuous_days > 0:
                formatted_lines.append(f"    - 连续放量天数 / Continuous Surge Days: {continuous_days}")
            
            bullish_prob = volume_surge.get("bullish_probability", 0)
            if bullish_prob > 0:
                formatted_lines.append(f"    - 看涨概率 / Bullish Probability: {bullish_prob}%")
                if bullish_prob >= 70:
                    formatted_lines.append(f"      → 高概率看涨信号 / High Probability Bullish Signal")
                elif bullish_prob >= 60:
                    formatted_lines.append(f"      → 中等概率看涨信号 / Medium Probability Bullish Signal")
            
            # 详细说明放量类型
            if volume_surge.get("is_bottom_surge", False):
                formatted_lines.append(f"    - 底部放量 / Bottom Surge: 是 / Yes")
                formatted_lines.append(f"      → 股票长期下跌后，在低位出现成交量大幅放大，可能是主力资金开始吸筹、准备启动行情的信号")
            if volume_surge.get("is_breakthrough_surge", False):
                formatted_lines.append(f"    - 突破压力位放量 / Breakthrough Surge: 是 / Yes")
                formatted_lines.append(f"      → 股价突破重要阻力位时成交量明显放大，说明多方力量强劲，可能继续上涨")
            if volume_surge.get("is_early_uptrend_surge", False):
                formatted_lines.append(f"    - 上涨初期持续放量 / Early Uptrend Surge: 是 / Yes")
                formatted_lines.append(f"      → 上涨初期成交量持续放大，表明市场关注度和参与度提升，可能延续上涨趋势")
        else:
            formatted_lines.append(f"  放量分析 / Volume Surge Analysis: 未检测到放量 / No volume surge detected")
        
        formatted_lines.append("-" * 60)
    
    return "\n".join(formatted_lines)


# 从 LLM 获取单个股票的短线交易决策
def generate_single_ticker_decision(
    ticker: str,
    position: dict,
    realized_gain: dict,
    current_price: float,
    fed_expectation: dict[str, float] | None,
    ticker_news: list[dict],
    ticker_technical: dict,
    ticker_price_trend: dict,
    ticker_recent_operations: list[dict],
    agent_id: str,
    state: AgentState,
) -> ShortTermDecision:
    """
    使用 LLM 生成单个股票的短线交易决策
    
    参数:
        ticker: 股票代码
        position: 该股票的持仓信息
        realized_gain: 该股票的已实现盈亏
        current_price: 该股票的当前价格
        fed_expectation: 美联储降息预期数据
        ticker_news: 该股票的相关新闻
        ticker_technical: 该股票的技术分析结果
        ticker_price_trend: 该股票的价格走势和量价关系分析
        ticker_recent_operations: 该股票近5天的历史操作记录
        agent_id: 代理 ID
        state: AgentState 对象
    
    返回:
        ShortTermDecision 对象，包含该股票的交易决策
    """
    # 格式化单个股票的持仓信息
    positions_dict = {ticker: position}
    realized_gains_dict = {ticker: realized_gain}
    positions_str = format_positions_for_prompt(positions_dict, realized_gains_dict)
    
    # 格式化单个股票的新闻信息
    filtered_news_by_ticker = {ticker: ticker_news}
    formatted_news = format_news_for_prompt(filtered_news_by_ticker)
    
    # 格式化单个股票的技术分析信息
    technical_analysis_dict = {ticker: ticker_technical} if ticker_technical else {}
    formatted_technical = format_technical_analysis_for_prompt(technical_analysis_dict)
    
    # 格式化单个股票的价格走势和量价关系分析信息
    price_trend_analysis_dict = {ticker: ticker_price_trend} if ticker_price_trend else {}
    formatted_price_trend = format_price_trend_analysis_for_prompt(price_trend_analysis_dict)
    
    # 格式化单个股票的历史操作记录
    recent_operations_dict = {ticker: ticker_recent_operations} if ticker_recent_operations else {}
    formatted_recent_operations = format_recent_operations_for_prompt(recent_operations_dict)
    
    # 构建给大模型的提示模板
    template = ChatPromptTemplate.from_messages(get_prompt_messages())
    
    # 构建提示数据
    prompt_data = {
        "positions": positions_str,
        "current_prices": json.dumps({ticker: current_price}, separators=(",", ":"), ensure_ascii=False),
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
    
    # 如果存在历史操作记录，添加到提示数据中
    if formatted_recent_operations:
        prompt_data["recent_operations"] = formatted_recent_operations
    else:
        prompt_data["recent_operations"] = "无历史操作记录 / No recent operations history"
    
    # 调用模板生成提示
    prompt = template.invoke(prompt_data)
    
    # 调试输出
    print(f"[{ticker}] 开始分析...")
    
    # 用于存储LLM调用时的错误信息
    llm_error_info = {"error": None, "failed": False}
    
    # 默认工厂函数：如果 LLM 失败，则返回持有决策
    def create_default_output():
        llm_error_info["failed"] = True
        error_msg = llm_error_info.get("error", "LLM调用失败（重试3次后仍失败）")
        decisions = {
            ticker: ShortTermDecision(
                action="hold",
                quantity=0,
                confidence=0,
                reasoning=f"LLM调用失败，使用默认决策：持有。失败原因: {error_msg}",
                suggested_price=None,
                time_window="5个交易日左右",
                score={},
            )
        }
        return ShortTermNewsAgentOutput(
            decisions=decisions,
            overall_assessment=f"无法生成分析，使用默认持有决策。LLM调用失败原因: {error_msg}",
        )
    
    # 调用 LLM 生成交易决策
    llm_out = call_llm(
        prompt=prompt,
        pydantic_model=ShortTermNewsAgentOutput,
        agent_name=agent_id,
        state=state,
        default_factory=create_default_output,
    )
    
    # 检查是否使用了默认输出
    if llm_error_info.get("failed", False):
        error_msg = llm_error_info.get("error") or "LLM调用失败（重试3次后仍失败，请查看上方错误信息）"
        print(f"\n⚠️ [{ticker}] LLM调用失败，已使用默认持有决策")
        print(f"失败原因: {error_msg}")
    
    # 获取该股票的决策（LLM 可能返回多个股票的决策，我们只取当前股票的）
    decision = llm_out.decisions.get(ticker)
    
    if not decision:
        # 如果 LLM 没有返回该股票的决策，创建一个默认的持有决策
        print(f"⚠️ [{ticker}] LLM 未返回该股票的决策，使用默认持有决策")
        decision = ShortTermDecision(
            action="hold",
            quantity=0,
            confidence=0,
            reasoning=f"LLM 未返回 {ticker} 的决策，使用默认持有决策",
            suggested_price=None,
            time_window="5个交易日左右",
            score={},
        )
    
    # 验证和修正建议价格（确保价格合理性）
    if current_price is not None:
        suggested_price = decision.suggested_price
        if suggested_price is not None:
            action = decision.action
            price_adjusted = False
            original_price = suggested_price
            
            if action == "buy":
                # 买入操作：建议价格必须 <= 当前价格
                if suggested_price > current_price:
                    decision.suggested_price = round(current_price * 0.99, 2)
                    price_adjusted = True
                    print(f"⚠️ [{ticker}] 买入建议价格不合理（${original_price:.2f} > 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
            
            elif action == "sell":
                # 卖出操作：建议价格必须 >= 当前价格
                if suggested_price < current_price:
                    decision.suggested_price = round(current_price * 1.01, 2)
                    price_adjusted = True
                    print(f"⚠️ [{ticker}] 卖出建议价格不合理（${original_price:.2f} < 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
            
            elif action == "short":
                # 做空操作：建议价格必须 >= 当前价格
                if suggested_price < current_price:
                    decision.suggested_price = round(current_price * 1.01, 2)
                    price_adjusted = True
                    print(f"⚠️ [{ticker}] 做空建议价格不合理（${original_price:.2f} < 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
            
            elif action == "cover":
                # 平仓操作：建议价格必须 <= 当前价格
                if suggested_price > current_price:
                    decision.suggested_price = round(current_price * 0.99, 2)
                    price_adjusted = True
                    print(f"⚠️ [{ticker}] 平仓建议价格不合理（${original_price:.2f} > 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
            
            # 如果价格被调整，在推理中添加说明
            if price_adjusted:
                decision.reasoning += f"\n\n【价格修正说明】：原建议价格${original_price:.2f}不合理（与当前价格${current_price:.2f}相比不符合{action}操作的逻辑），已自动修正为${decision.suggested_price:.2f}。"
    
    print(f"[{ticker}] 分析完成 - 操作: {decision.action}, 信心度: {decision.confidence}%")
    
    return decision


# 从 LLM 获取短线交易决策（批量分析，保留用于兼容性）
def generate_short_term_decision(
    positions: dict,
    realized_gains: dict,
    tickers: list[str],
    current_prices: dict[str, float],
    fed_expectation: dict[str, float] | None,
    filtered_news_by_ticker: dict[str, list[dict]],
    technical_analysis: dict,
    price_trend_analysis: dict,
    recent_operations: dict,
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
        recent_operations: 近5天的历史操作记录字典
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
    
    # 格式化历史操作记录
    formatted_recent_operations = format_recent_operations_for_prompt(recent_operations)
    
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
    
    # 如果存在历史操作记录，添加到提示数据中
    if formatted_recent_operations:
        prompt_data["recent_operations"] = formatted_recent_operations
    else:
        prompt_data["recent_operations"] = "无历史操作记录 / No recent operations history"
    
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
    
    # 验证和修正建议价格（确保价格合理性）
    for ticker, decision in llm_out.decisions.items():
        current_price = current_prices.get(ticker)
        if current_price is None:
            # 如果没有当前价格，无法验证，跳过
            continue
        
        # 获取建议价格
        suggested_price = decision.suggested_price
        if suggested_price is None:
            # 如果没有建议价格，跳过
            continue
        
        # 根据操作类型验证和修正建议价格
        action = decision.action
        price_adjusted = False
        original_price = suggested_price
        
        if action == "buy":
            # 买入操作：建议价格必须 <= 当前价格
            if suggested_price > current_price:
                # 价格不合理，修正为当前价格的99%
                decision.suggested_price = round(current_price * 0.99, 2)
                price_adjusted = True
                print(f"⚠️  {ticker} 买入建议价格不合理（${original_price:.2f} > 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
        
        elif action == "sell":
            # 卖出操作：建议价格必须 >= 当前价格
            if suggested_price < current_price:
                # 价格不合理，修正为当前价格的101%
                decision.suggested_price = round(current_price * 1.01, 2)
                price_adjusted = True
                print(f"⚠️  {ticker} 卖出建议价格不合理（${original_price:.2f} < 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
        
        elif action == "short":
            # 做空操作：建议价格必须 >= 当前价格
            if suggested_price < current_price:
                # 价格不合理，修正为当前价格的101%
                decision.suggested_price = round(current_price * 1.01, 2)
                price_adjusted = True
                print(f"⚠️  {ticker} 做空建议价格不合理（${original_price:.2f} < 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
        
        elif action == "cover":
            # 平仓操作：建议价格必须 <= 当前价格
            if suggested_price > current_price:
                # 价格不合理，修正为当前价格的99%
                decision.suggested_price = round(current_price * 0.99, 2)
                price_adjusted = True
                print(f"⚠️  {ticker} 平仓建议价格不合理（${original_price:.2f} > 当前价格${current_price:.2f}），已自动修正为${decision.suggested_price:.2f}")
        
        # 如果价格被调整，在推理中添加说明
        if price_adjusted:
            decision.reasoning += f"\n\n【价格修正说明】：原建议价格${original_price:.2f}不合理（与当前价格${current_price:.2f}相比不符合{action}操作的逻辑），已自动修正为${decision.suggested_price:.2f}。"
    
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
    
    # 保存技术分析和价格走势数据供后续使用（如企业微信消息格式化）
    state["data"]["technical_analysis_for_alert"] = technical_analysis
    state["data"]["price_trend_analysis_for_alert"] = price_trend_analysis
    
    return llm_out


##### 短线新闻分析代理主函数 - 逐个股票分析版本 #####
def short_term_news_agent_single_ticker(
    ticker: str,
    state: AgentState,
    agent_id: str = "short_term_news_agent"
) -> dict:
    """
    分析单个股票的消息面影响，并提供短线交易建议
    
    参数:
        ticker: 要分析的股票代码
        state: AgentState 对象，包含数据、消息和元数据
        agent_id: 代理 ID，用于进度跟踪和模型配置
    
    返回:
        包含该股票决策和分析数据的字典
    """
    # 从 mycount.py 获取持仓信息
    positions = initial_positions
    realized_gains = initial_realized_gains
    
    # 获取该股票的持仓信息
    position = positions.get(ticker, {"long": 0, "long_cost_basis": 0.0, "short": 0, "short_cost_basis": 0.0})
    realized_gain = realized_gains.get(ticker, {"long": 0.0, "short": 0.0})
    
    # 获取美联储降息预期数据（全局数据，所有股票共享）
    fed_expectation = state["data"].get("fed_rate_cut_expectation")
    if not fed_expectation:
        fed_expectation = get_fed_rate_cut_expectation()
        print(f"[{ticker}] 联储降息预期", fed_expectation)
        state["data"]["fed_rate_cut_expectation"] = fed_expectation
    
    # 使用新闻管理代理筛选该股票的相关新闻（只使用近5天的新闻）
    filtered_news_by_ticker = filter_news_for_tickers([ticker], agent_id, state, days=5, use_progress=False)
    ticker_news = filtered_news_by_ticker.get(ticker, [])
    print(f"[{ticker}] 新闻筛选完成（5天内），相关新闻数量: {len(ticker_news)}")
    
    # 再次过滤，只保留近2小时内的新闻（防止重复发送旧新闻）
    filtered_news_by_ticker_2h = filter_news_by_hours({ticker: ticker_news}, hours=2)
    ticker_news = filtered_news_by_ticker_2h.get(ticker, [])
    print(f"[{ticker}] 新闻筛选完成（2小时内），相关新闻数量: {len(ticker_news)}")
    
    # 调用技术分析代理获取该股票的技术面分析结果
    # 确保 state 中有必要的日期信息
    if "start_date" not in state["data"] or "end_date" not in state["data"]:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        state["data"]["start_date"] = start_date
        state["data"]["end_date"] = end_date
    
    # 确保 state 中有 tickers
    state["data"]["tickers"] = [ticker]
    
    # 确保 state 中有 analyst_signals 字典
    if "analyst_signals" not in state["data"]:
        state["data"]["analyst_signals"] = {}
    
    # 调用技术分析代理获取技术面分析结果
    ticker_technical = {}
    try:
        print(f"[{ticker}] 开始技术分析...")
        # 调用技术分析代理
        technical_state = technical_analyst_agent(state, agent_id="technical_analyst_agent")
        # 更新 state 以包含技术分析结果
        state["data"] = technical_state["data"]
        technical_analysis = state["data"].get("analyst_signals", {}).get("technical_analyst_agent", {})
        ticker_technical = technical_analysis.get(ticker, {})
        print(f"[{ticker}] 技术分析完成")
    except Exception as e:
        print(f"⚠️ [{ticker}] 技术分析失败: {e}")
        ticker_technical = {}
    
    # 从状态中获取当前价格
    current_prices = state["data"].get("current_prices", {})
    current_price = current_prices.get(ticker)
    
    # 获取最近价格走势和量价关系分析（使用2小时K线）
    ticker_price_trend = {}
    try:
        print(f"[{ticker}] 开始分析价格走势和量价关系（2小时K线）...")
        api_key = get_api_key_from_state(state, "FINANCIAL_DATASETS_API_KEY")
        # 获取最近5天的2小时K线数据用于分析
        end_date = state["data"].get("end_date", datetime.now().strftime("%Y-%m-%d"))
        start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
        
        prices = get_prices(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            period=Period.Min_120,  # 使用2小时K线
            api_key=api_key,
        )
        if prices and len(prices) >= 5:
            ticker_price_trend = analyze_price_trend_and_volume(prices)
        else:
            ticker_price_trend = {"error": "数据不足"}
        print(f"[{ticker}] 价格走势分析完成")
    except Exception as e:
        print(f"⚠️ [{ticker}] 价格走势分析失败: {e}")
        ticker_price_trend = {"error": str(e)}
    
    # 加载近5天的历史操作记录作为参考
    from src.tools.alert_utils import load_recent_operations_history
    recent_operations = load_recent_operations_history(days=5)
    ticker_recent_operations = recent_operations.get(ticker, [])
    
    # 调用生成单个股票交易决策函数
    decision = generate_single_ticker_decision(
        ticker=ticker,
        position=position,
        realized_gain=realized_gain,
        current_price=current_price,
        fed_expectation=fed_expectation,
        ticker_news=ticker_news,
        ticker_technical=ticker_technical,
        ticker_price_trend=ticker_price_trend,
        ticker_recent_operations=ticker_recent_operations,
        agent_id=agent_id,
        state=state,
    )
    
    # 返回该股票的决策和分析数据
    return {
        "ticker": ticker,
        "decision": decision,
        "fed_expectation": fed_expectation,
        "ticker_news": ticker_news,
        "ticker_technical": ticker_technical,
        "ticker_price_trend": ticker_price_trend,
        "current_price": current_price,
    }


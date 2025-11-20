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
    
    # 从状态中获取当前价格（如果存在）
    current_prices = state["data"].get("current_prices", {})
    
    # 调用生成交易决策函数
    result = generate_short_term_decision(
        positions=positions,
        realized_gains=realized_gains,
        tickers=tickers,
        current_prices=current_prices,
        fed_expectation=fed_expectation,
        filtered_news_by_ticker=filtered_news_by_ticker,
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


# 从 LLM 获取短线交易决策
def generate_short_term_decision(
    positions: dict,
    realized_gains: dict,
    tickers: list[str],
    current_prices: dict[str, float],
    fed_expectation: dict[str, float] | None,
    filtered_news_by_ticker: dict[str, list[dict]],
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
        agent_id: 代理 ID
        state: AgentState 对象
    
    返回:
        ShortTermNewsAgentOutput 对象，包含交易决策
    """
    # 格式化持仓信息
    positions_str = format_positions_for_prompt(positions, realized_gains)
    
    # 格式化新闻信息
    formatted_news = format_news_for_prompt(filtered_news_by_ticker)
    
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
    
    # 调用模板生成提示
    prompt = template.invoke(prompt_data)
    
    # 调试输出
    print("短线新闻分析 >", "持仓数量:", len(positions), "股票数量:", len(tickers))
    print("*" * 100)
    
    # 默认工厂函数：如果 LLM 失败，则将所有股票填充为持有
    def create_default_output():
        decisions = {}
        for ticker in tickers:
            decisions[ticker] = ShortTermDecision(
                action="hold",
                quantity=0,
                confidence=0,
                reasoning="默认决策：持有",
                suggested_price=None,
                time_window="5个交易日左右",
                score={},
            )
        return ShortTermNewsAgentOutput(
            decisions=decisions,
            overall_assessment="无法生成分析，使用默认持有决策",
        )
    
    # 调用 LLM 生成交易决策
    llm_out = call_llm(
        prompt=prompt,
        pydantic_model=ShortTermNewsAgentOutput,
        agent_name=agent_id,
        state=state,
        default_factory=create_default_output,
    )
    
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


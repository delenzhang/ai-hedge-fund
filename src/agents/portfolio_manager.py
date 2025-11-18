# 导入 JSON 处理模块，用于序列化和反序列化数据
import json
# 导入时间模块（当前未使用，但保留用于可能的延迟或时间戳功能）
import time
# 导入 LangChain 的 HumanMessage 类，用于创建人类消息对象
from langchain_core.messages import HumanMessage
# 导入 LangChain 的 ChatPromptTemplate 类，用于创建聊天提示模板
from langchain_core.prompts import ChatPromptTemplate

# 导入 AgentState 类型和 show_agent_reasoning 函数
# AgentState 格式: {"data": {...}, "messages": [...], "metadata": {...}}
from src.graph.state import AgentState, show_agent_reasoning
# 导入 Pydantic 的 BaseModel 和 Field，用于数据验证和模型定义
from pydantic import BaseModel, Field
# 导入 Literal 类型，用于定义字面量类型约束
from typing_extensions import Literal
# 导入进度跟踪模块，用于更新代理执行状态
from src.utils.progress import progress
# 导入 LLM 调用函数，用于调用大语言模型
from src.utils.llm import call_llm
# 导入投资组合经理的提示消息生成函数
from src.agents.contexts.portfolio_manager import get_prompt_messages
# 导入获取美联储降息预期数据的函数
from src.tools.data_api import get_fed_rate_cut_expectation


# 定义投资组合决策数据模型
# 运行时数据格式示例: {"action": "buy", "quantity": 100, "confidence": 85, "reasoning": "...", "suggested_price": 150.5}
class PortfolioDecision(BaseModel):
    # 交易动作类型：买入、卖出、做空、平仓、持有
    # 运行时值: "buy" | "sell" | "short" | "cover" | "hold"
    action: Literal["buy", "sell", "short", "cover", "hold"]
    # 交易数量（股数）
    # 运行时值: 整数，例如 100, 50, 0
    quantity: int = Field(description="Number of shares to trade")
    # 信心度（0-100）
    # 运行时值: 0-100 的整数，例如 85, 90, 50
    confidence: int = Field(description="Confidence 0-100")
    # 决策推理说明
    # 运行时值: 字符串，例如 "基于技术分析，建议买入"
    reasoning: str = Field(description="Reasoning for the decision")
    # 建议的交易价格（可选）
    # 运行时值: 浮点数或 None，例如 150.5, 200.0, None
    suggested_price: float | None = Field(default=None, description="Suggested buy/sell price per share (optional)")


# 定义投资组合经理输出数据模型
# 运行时数据格式示例: {"decisions": {"PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...)}}
class PortfolioManagerOutput(BaseModel):
    # 股票代码到交易决策的字典映射
    # 运行时值: {"PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...), ...}
    decisions: dict[str, PortfolioDecision] = Field(description="Dictionary of ticker to trading decisions")


##### 投资组合管理代理主函数 #####
# state 运行时格式: {
#   "data": {
#     "portfolio": {"cash": 100000.0, "positions": {...}, "equity": 150000.0, ...},
#     "analyst_signals": {"aswath_damodaran_agent": {"PYPL": {"signal": "bullish", "confidence": 85, ...}}, ...},
#     "tickers": ["PYPL", "BABA", ...]
#   },
#   "messages": [...],
#   "metadata": {"show_reasoning": True/False, ...}
# }
# agent_id 运行时值: "portfolio_manager" 或 "portfolio_manager_xxx"
def portfolio_management_agent(state: AgentState, agent_id: str = "portfolio_manager"):
    """为多个股票代码做出最终交易决策并生成订单"""
    
    # 从状态中提取投资组合信息
    # 运行时格式: {"cash": 100000.0, "positions": {"PYPL": {"long": 100, ...}}, "equity": 150000.0, "margin_requirement": 0.5, "margin_used": 0.0}
    portfolio = state["data"]["portfolio"]
    # 从状态中提取分析师信号
    # 运行时格式: {"aswath_damodaran_agent": {"PYPL": {"signal": "bullish", "confidence": 85, "reasoning": "..."}}, "risk_management_agent": {"PYPL": {"remaining_position_limit": 50000.0, "current_price": 150.5}}, ...}
    analyst_signals = state["data"]["analyst_signals"]
    # 从状态中提取股票代码列表
    # 运行时值: ["PYPL", "BABA", "NIO", ...]
    tickers = state["data"]["tickers"]

    # 初始化存储字典
    # position_limits 运行时格式: {"PYPL": 50000.0, "BABA": 30000.0, ...} - 每个股票的剩余持仓限额（美元）
    position_limits = {}
    # current_prices 运行时格式: {"PYPL": 150.5, "BABA": 80.2, ...} - 每个股票的当前价格（美元）
    current_prices = {}
    # max_shares 运行时格式: {"PYPL": 332, "BABA": 374, ...} - 每个股票的最大可交易股数
    max_shares = {}
    # signals_by_ticker 运行时格式: {"PYPL": {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, ...}, ...}
    signals_by_ticker = {}
    
    # 遍历每个股票代码，处理分析师信号和风险数据
    for ticker in tickers:
        # 更新进度状态：正在处理分析师信号
        progress.update_status(agent_id, ticker, "Processing analyst signals")

        # 查找对应的风险管理代理 ID
        # 如果 agent_id 以 "portfolio_manager_" 开头，提取后缀并构造对应的风险代理 ID
        if agent_id.startswith("portfolio_manager_"):
            # 提取后缀，例如 "portfolio_manager_1" -> "1"
            suffix = agent_id.split('_')[-1]
            # 构造对应的风险代理 ID，例如 "risk_management_agent_1"
            risk_manager_id = f"risk_management_agent_{suffix}"
        else:
            # CLI 模式的回退：使用默认的风险代理 ID
            risk_manager_id = "risk_management_agent"  # CLI 模式的回退

        # 从分析师信号中获取风险数据
        # risk_data 运行时格式: {"remaining_position_limit": 50000.0, "current_price": 150.5, "volatility": 0.25, ...}
        risk_data = analyst_signals.get(risk_manager_id, {}).get(ticker, {})
        # 提取剩余持仓限额（美元）
        # 运行时值: 浮点数，例如 50000.0, 30000.0
        position_limits[ticker] = risk_data.get("remaining_position_limit", 0.0)
        # 提取当前价格（美元），并转换为浮点数
        # 运行时值: 浮点数，例如 150.5, 80.2
        current_prices[ticker] = float(risk_data.get("current_price", 0.0))

        # 根据持仓限额和价格计算最大允许交易股数
        if current_prices[ticker] > 0:
            # 计算最大股数：持仓限额除以当前价格（向下取整）
            # 例如: 50000.0 / 150.5 = 332.23 -> 332
            max_shares[ticker] = int(position_limits[ticker] // current_prices[ticker])
        else:
            # 如果价格为 0，则最大股数为 0
            max_shares[ticker] = 0

        # 压缩分析师信号为 {sig, conf} 格式，减少 token 使用
        # ticker_signals 运行时格式: {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, "ben_graham_agent": {"sig": "neutral", "conf": 60}, ...}
        ticker_signals = {}
        # 遍历所有分析师信号
        for agent, signals in analyst_signals.items():
            # 排除风险管理代理，只处理分析师代理的信号
            if not agent.startswith("risk_management_agent") and ticker in signals:
                # 提取信号类型：bullish, bearish, neutral
                sig = signals[ticker].get("signal")
                # 提取信心度：0-100
                conf = signals[ticker].get("confidence")
                # 如果信号和信心度都存在，则添加到压缩信号中
                if sig is not None and conf is not None:
                    # 使用简短的键名 "sig" 和 "conf" 以减少 token
                    ticker_signals[agent] = {"sig": sig, "conf": conf}
        # 将压缩后的信号存储到按股票代码索引的字典中
        signals_by_ticker[ticker] = ticker_signals

    # 将当前价格存储到状态中，供后续使用
    state["data"]["current_prices"] = current_prices

    # 获取美联储降息预期数据
    # fed_expectation 运行时格式: {"cut_25bp": 0.43, "cut_50bp_or_more": 0.018, "no_change": 0.54, "hike": 0.001, "total_cut_probability": 0.448}
    fed_expectation = get_fed_rate_cut_expectation()
    print("联储降息", fed_expectation)
    # 将降息预期数据存储到状态中
    state["data"]["fed_rate_cut_expectation"] = fed_expectation

    # 更新进度状态：正在生成交易决策
    progress.update_status(agent_id, None, "Generating trading decisions")

    # 调用生成交易决策函数
    # result 运行时格式: PortfolioManagerOutput(decisions={"PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...)})
    result = generate_trading_decision(
        tickers=tickers,  # ["PYPL", "BABA", ...]
        signals_by_ticker=signals_by_ticker,  # {"PYPL": {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, ...}, ...}
        current_prices=current_prices,  # {"PYPL": 150.5, "BABA": 80.2, ...}
        max_shares=max_shares,  # {"PYPL": 332, "BABA": 374, ...}
        portfolio=portfolio,  # {"cash": 100000.0, "positions": {...}, ...}
        agent_id=agent_id,  # "portfolio_manager" 或 "portfolio_manager_xxx"
        state=state,  # 完整的 AgentState 对象
        fed_expectation=fed_expectation,  # 美联储降息预期数据
    )
    
    # 创建 HumanMessage 对象，包含交易决策的 JSON 序列化内容
    # content 运行时格式: '{"PYPL": {"action": "buy", "quantity": 100, "confidence": 85, ...}, "BABA": {...}}'
    message = HumanMessage(
        content=json.dumps({ticker: decision.model_dump() for ticker, decision in result.decisions.items()}),
        name=agent_id,  # 消息的发送者名称
    )

    # 如果启用了推理显示，则显示代理的推理过程
    if state["metadata"]["show_reasoning"]:
        # 显示投资组合经理的推理过程
        show_agent_reasoning({ticker: decision.model_dump() for ticker, decision in result.decisions.items()},
                             "Portfolio Manager")

    # 更新进度状态：完成
    progress.update_status(agent_id, None, "Done")

    # 返回更新后的状态，包含新消息和更新后的数据
    return {
        "messages": state["messages"] + [message],  # 将新消息添加到消息列表
        "data": state["data"],  # 返回更新后的数据
    }


# 计算每个股票允许的交易操作和最大数量（确定性计算）
# tickers 运行时格式: ["PYPL", "BABA", "NIO", ...] - 股票代码列表
# current_prices 运行时格式: {"PYPL": 150.5, "BABA": 80.2, ...} - 当前价格字典
# max_shares 运行时格式: {"PYPL": 332, "BABA": 374, ...} - 最大可交易股数字典
# portfolio 运行时格式: {
#   "cash": 100000.0,  # 现金余额（美元）
#   "positions": {  # 持仓信息
#     "PYPL": {"long": 100, "long_cost_basis": 15000.0, "short": 0, "short_cost_basis": 0.0},
#     "BABA": {"long": 0, "long_cost_basis": 0.0, "short": 50, "short_cost_basis": 4000.0}
#   },
#   "margin_requirement": 0.5,  # 保证金要求比例（50%）
#   "margin_used": 0.0,  # 已使用的保证金（美元）
#   "equity": 150000.0  # 权益（美元）
# }
# 返回值运行时格式: {
#   "PYPL": {"buy": 332, "sell": 100, "hold": 0},  # 允许买入332股，卖出100股
#   "BABA": {"short": 374, "cover": 50, "hold": 0},  # 允许做空374股，平仓50股
#   "NIO": {"hold": 0}  # 只能持有
# }
def compute_allowed_actions(
        tickers: list[str],
        current_prices: dict[str, float],
        max_shares: dict[str, int],
        portfolio: dict[str, float],
) -> dict[str, dict[str, int]]:
    """确定性计算每个股票允许的交易操作和最大数量"""
    
    # 初始化允许操作的字典
    # allowed 运行时格式: {"PYPL": {"buy": 332, "sell": 100, ...}, ...}
    allowed = {}
    # 提取现金余额（美元）
    # 运行时值: 浮点数，例如 100000.0
    cash = float(portfolio.get("cash", 0.0))
    # 提取持仓信息
    # 运行时格式: {"PYPL": {"long": 100, "long_cost_basis": 15000.0, "short": 0, "short_cost_basis": 0.0}, ...}
    positions = portfolio.get("positions", {}) or {}
    # 提取保证金要求比例（例如 0.5 表示 50%）
    # 运行时值: 浮点数，例如 0.5, 0.3
    margin_requirement = float(portfolio.get("margin_requirement", 0.5))
    # 提取已使用的保证金（美元）
    # 运行时值: 浮点数，例如 0.0, 5000.0
    margin_used = float(portfolio.get("margin_used", 0.0))
    # 提取权益（美元），如果没有则使用现金
    # 运行时值: 浮点数，例如 150000.0
    equity = float(portfolio.get("equity", cash))

    # 遍历每个股票代码
    for ticker in tickers:
        # 获取当前价格（美元）
        # 运行时值: 浮点数，例如 150.5, 80.2
        price = float(current_prices.get(ticker, 0.0))
        # 获取该股票的持仓信息，如果没有则使用默认值
        # pos 运行时格式: {"long": 100, "long_cost_basis": 15000.0, "short": 0, "short_cost_basis": 0.0}
        pos = positions.get(
            ticker,
            {"long": 0, "long_cost_basis": 0.0, "short": 0, "short_cost_basis": 0.0},
        )
        # 提取多头持仓股数
        # 运行时值: 整数，例如 100, 0
        long_shares = int(pos.get("long", 0) or 0)
        # 提取空头持仓股数
        # 运行时值: 整数，例如 0, 50
        short_shares = int(pos.get("short", 0) or 0)
        # 提取最大可交易股数（来自风险管理的限制）
        # 运行时值: 整数，例如 332, 374
        max_qty = int(max_shares.get(ticker, 0) or 0)

        # 初始化所有操作的数量为 0
        # actions 运行时格式: {"buy": 0, "sell": 0, "short": 0, "cover": 0, "hold": 0}
        actions = {"buy": 0, "sell": 0, "short": 0, "cover": 0, "hold": 0}

        # 处理多头侧（买入/卖出）
        # 如果有多头持仓，则可以卖出
        if long_shares > 0:
            # 可以卖出的数量等于当前多头持仓数量
            actions["sell"] = long_shares
        # 如果有现金且价格大于 0，则可以买入
        if cash > 0 and price > 0:
            # 计算基于现金的最大买入数量（向下取整）
            # 例如: 100000.0 / 150.5 = 664.45 -> 664
            max_buy_cash = int(cash // price)
            # 最大买入数量 = min(风险管理限制, 现金限制)
            # 例如: min(332, 664) = 332
            max_buy = max(0, min(max_qty, max_buy_cash))
            # 如果最大买入数量大于 0，则设置买入操作
            if max_buy > 0:
                actions["buy"] = max_buy

        # 处理空头侧（做空/平仓）
        # 如果有空头持仓，则可以平仓
        if short_shares > 0:
            # 可以平仓的数量等于当前空头持仓数量
            actions["cover"] = short_shares
        # 如果价格大于 0 且最大数量大于 0，则可以做空
        if price > 0 and max_qty > 0:
            # 如果保证金要求为 0 或未设置，则只受最大数量限制
            if margin_requirement <= 0.0:
                # 如果保证金要求为零或未设置，则只受最大数量限制
                max_short = max_qty
            else:
                # 计算可用保证金：权益/保证金要求 - 已使用保证金
                # 例如: (150000.0 / 0.5) - 0.0 = 300000.0
                available_margin = max(0.0, (equity / margin_requirement) - margin_used)
                # 计算基于保证金的做空数量（向下取整）
                # 例如: 300000.0 / 150.5 = 1993.35 -> 1993
                max_short_margin = int(available_margin // price)
                # 最大做空数量 = min(风险管理限制, 保证金限制)
                # 例如: min(332, 1993) = 332
                max_short = max(0, min(max_qty, max_short_margin))
            # 如果最大做空数量大于 0，则设置做空操作
            if max_short > 0:
                actions["short"] = max_short

        # 持有操作始终有效（数量为 0）
        actions["hold"] = 0

        # 修剪零容量的操作以减少 token 使用，但保留 hold
        # pruned 运行时格式: {"hold": 0, "buy": 332, "sell": 100} 或 {"hold": 0}
        pruned = {"hold": 0}
        # 遍历所有操作
        for k, v in actions.items():
            # 如果不是 hold 且数量大于 0，则保留该操作
            if k != "hold" and v > 0:
                pruned[k] = v

        # 将修剪后的操作存储到允许操作字典中
        allowed[ticker] = pruned

    # 返回允许操作的字典
    return allowed


# 压缩信号数据，只保留 {agent: {sig, conf}} 格式并丢弃空代理
# signals_by_ticker 运行时格式: {
#   "PYPL": {
#     "aswath_damodaran_agent": {"sig": "bullish", "conf": 85},
#     "ben_graham_agent": {"sig": "neutral", "conf": 60},
#     "warren_buffett_agent": {"signal": "bullish", "confidence": 90}  # 可能使用完整键名
#   },
#   "BABA": {...}
# }
# 返回值运行时格式: {
#   "PYPL": {
#     "aswath_damodaran_agent": {"sig": "bullish", "conf": 85},
#     "ben_graham_agent": {"sig": "neutral", "conf": 60},
#     "warren_buffett_agent": {"sig": "bullish", "conf": 90}  # 统一转换为简写格式
#   },
#   "BABA": {...}
# }
def _compact_signals(signals_by_ticker: dict[str, dict]) -> dict[str, dict]:
    """只保留 {agent: {sig, conf}} 格式并丢弃空代理"""
    
    # 初始化输出字典
    # out 运行时格式: {"PYPL": {...}, "BABA": {...}, ...}
    out = {}
    # 遍历每个股票代码和对应的代理信号
    for t, agents in signals_by_ticker.items():
        # 如果没有代理信号，则设置为空字典
        if not agents:
            out[t] = {}
            continue
        # 初始化压缩后的信号字典
        # compact 运行时格式: {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, ...}
        compact = {}
        # 遍历每个代理和其负载数据
        for agent, payload in agents.items():
            # 尝试获取信号（优先使用简写 "sig"，如果没有则使用完整 "signal"）
            # 运行时值: "bullish" | "bearish" | "neutral"
            sig = payload.get("sig") or payload.get("signal")
            # 尝试获取信心度（优先使用简写 "conf"，如果没有则使用完整 "confidence"）
            # 运行时值: 0-100 的整数
            conf = payload.get("conf") if "conf" in payload else payload.get("confidence")
            # 如果信号和信心度都存在，则添加到压缩字典中
            if sig is not None and conf is not None:
                # 统一使用简写格式以减少 token
                compact[agent] = {"sig": sig, "conf": conf}
        # 将压缩后的信号存储到输出字典中
        out[t] = compact
    # 返回压缩后的信号字典
    return out


# 从 LLM 获取交易决策（使用确定性约束和最小化提示）
# tickers 运行时格式: ["PYPL", "BABA", "NIO", ...] - 股票代码列表
# signals_by_ticker 运行时格式: {
#   "PYPL": {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, ...},
#   "BABA": {...},
#   ...
# } - 按股票代码索引的分析师信号
# current_prices 运行时格式: {"PYPL": 150.5, "BABA": 80.2, ...} - 当前价格字典
# max_shares 运行时格式: {"PYPL": 332, "BABA": 374, ...} - 最大可交易股数字典
# portfolio 运行时格式: {
#   "cash": 100000.0,
#   "positions": {...},
#   "equity": 150000.0,
#   "margin_requirement": 0.5,
#   "margin_used": 0.0
# } - 投资组合信息
# agent_id 运行时值: "portfolio_manager" 或 "portfolio_manager_xxx" - 代理 ID
# state 运行时格式: 完整的 AgentState 对象，包含 data、messages、metadata
# fed_expectation 运行时格式: {"cut_25bp": 0.43, "cut_50bp_or_more": 0.018, "no_change": 0.54, "hike": 0.001, "total_cut_probability": 0.448} - 美联储降息预期
# 返回值运行时格式: PortfolioManagerOutput(decisions={"PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...)})
def generate_trading_decision(
        tickers: list[str],
        signals_by_ticker: dict[str, dict],
        current_prices: dict[str, float],
        max_shares: dict[str, int],
        portfolio: dict[str, float],
        agent_id: str,
        state: AgentState,
        fed_expectation: dict[str, float] | None = None,
) -> PortfolioManagerOutput:
    """使用确定性约束和最小化提示从 LLM 获取决策"""

    # 确定性约束：计算所有股票允许的操作
    # allowed_actions_full 运行时格式: {
    #   "PYPL": {"buy": 332, "sell": 100, "hold": 0},
    #   "BABA": {"short": 374, "cover": 50, "hold": 0},
    #   "NIO": {"hold": 0}  # 只能持有
    # }
    allowed_actions_full = compute_allowed_actions(tickers, current_prices, max_shares, portfolio)

    # 预填充纯持有决策，避免将它们发送给 LLM
    # prefilled_decisions 运行时格式: {"NIO": PortfolioDecision(action="hold", quantity=0, ...), ...}
    prefilled_decisions: dict[str, PortfolioDecision] = {}
    # tickers_for_llm 运行时格式: ["PYPL", "BABA", ...] - 需要发送给 LLM 的股票代码列表
    tickers_for_llm: list[str] = []
    # 遍历所有股票代码
    for t in tickers:
        # 获取该股票允许的操作，如果没有则默认为 {"hold": 0}
        # aa 运行时格式: {"buy": 332, "sell": 100, "hold": 0} 或 {"hold": 0}
        aa = allowed_actions_full.get(t, {"hold": 0})
        # 如果只有 'hold' 键存在，则没有可执行的交易
        if set(aa.keys()) == {"hold"}:
            # 预填充持有决策，信心度为 100%
            prefilled_decisions[t] = PortfolioDecision(
                action="hold",  # 持有操作
                quantity=0,  # 数量为 0
                confidence=100.0,  # 信心度 100%
                reasoning="No valid trade available",  # 推理：没有可用的有效交易
                suggested_price=None  # 无建议价格
            )
        else:
            # 如果有其他操作可用，则添加到需要发送给 LLM 的列表
            tickers_for_llm.append(t)

    # 如果所有股票都只能持有，则直接返回预填充的决策
    if not tickers_for_llm:
        return PortfolioManagerOutput(decisions=prefilled_decisions)

    # 只为发送给 LLM 的股票构建压缩负载
    # compact_signals 运行时格式: {
    #   "PYPL": {"aswath_damodaran_agent": {"sig": "bullish", "conf": 85}, ...},
    #   "BABA": {...}
    # } - 只包含需要 LLM 处理的股票
    compact_signals = _compact_signals({t: signals_by_ticker.get(t, {}) for t in tickers_for_llm})
    # compact_allowed 运行时格式: {
    #   "PYPL": {"buy": 332, "sell": 100, "hold": 0},
    #   "BABA": {"short": 374, "cover": 50, "hold": 0}
    # } - 只包含需要 LLM 处理的股票
    compact_allowed = {t: allowed_actions_full[t] for t in tickers_for_llm}
    # compact_prices 运行时格式: {"PYPL": 150.5, "BABA": 80.2} - 只包含需要 LLM 处理的股票
    compact_prices = {t: current_prices.get(t, 0.0) for t in tickers_for_llm}

    # 构建给大模型的提示模板
    # 这个提示用于让大模型作为投资组合经理，基于分析师信号和允许的操作做出交易决策
    template = ChatPromptTemplate.from_messages(get_prompt_messages())

    # 构建提示数据
    # prompt_data 运行时格式: {
    #   "signals": '{"PYPL":{"aswath_damodaran_agent":{"sig":"bullish","conf":85},...},"BABA":{...}}',
    #   "allowed": '{"PYPL":{"buy":332,"sell":100,"hold":0},"BABA":{...}}',
    #   "prices": '{"PYPL":150.5,"BABA":80.2}',
    #   "fed_expectation": '{"cut_25bp":0.43,"cut_50bp_or_more":0.018,"no_change":0.54,"hike":0.001,"total_cut_probability":0.448}'
    # }
    prompt_data = {
        "signals": json.dumps(compact_signals, separators=(",", ":"), ensure_ascii=False),  # 紧凑 JSON，无空格，保留中文字符
        "allowed": json.dumps(compact_allowed, separators=(",", ":"), ensure_ascii=False),  # 紧凑 JSON，无空格
        "prices": json.dumps(compact_prices, separators=(",", ":"), ensure_ascii=False),  # 紧凑 JSON，无空格
    }
    # 如果存在降息预期数据，添加到提示数据中
    if fed_expectation:
        prompt_data["fed_expectation"] = json.dumps(fed_expectation, separators=(",", ":"), ensure_ascii=False)
    else:
        prompt_data["fed_expectation"] = "null"
    # 调用模板生成提示
    prompt = template.invoke(prompt_data)
    # 调试输出：打印信号数据（临时，用于调试）
    print("signals>", prompt_data)
    print("*"*100)

    # 默认工厂函数：如果 LLM 失败，则将所有剩余股票填充为持有
    def create_default_portfolio_output():
        # 从预填充的决策开始
        # decisions 运行时格式: {"NIO": PortfolioDecision(...), "PYPL": PortfolioDecision(...), ...}
        decisions = dict(prefilled_decisions)
        # 为需要 LLM 处理的股票创建默认持有决策
        for t in tickers_for_llm:
            decisions[t] = PortfolioDecision(
                action="hold",  # 默认持有
                quantity=0,  # 数量为 0
                confidence=0.0,  # 信心度为 0
                reasoning="Default decision: hold",  # 推理：默认决策为持有
                suggested_price=None  # 无建议价格
            )
        # 返回包含所有决策的 PortfolioManagerOutput
        return PortfolioManagerOutput(decisions=decisions)

    # 调用 LLM 生成交易决策
    # llm_out 运行时格式: PortfolioManagerOutput(decisions={"PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...)})
    llm_out = call_llm(
        prompt=prompt,  # 生成的提示对象
        pydantic_model=PortfolioManagerOutput,  # 期望的返回模型类型
        agent_name=agent_id,  # 代理名称
        state=state,  # 完整状态对象
        default_factory=create_default_portfolio_output,  # 失败时的默认工厂函数
    )
    
    # 保存 LLM 的完整分析内容到状态中，供展示使用
    # 将决策转换为字典格式，包含完整的推理信息
    # 注意：这里保存的是LLM返回的完整决策信息，包括详细的reasoning
    llm_analysis_content = {}
    for ticker, decision in llm_out.decisions.items():
        # 保存完整的决策信息，包括详细的推理
        llm_analysis_content[ticker] = {
            "action": decision.action,
            "quantity": decision.quantity,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning,  # 这是LLM生成的完整推理
            "suggested_price": decision.suggested_price,
        }
        # 如果推理很短，可能是默认值，尝试从决策中获取更详细的信息
        if not decision.reasoning or len(decision.reasoning) < 20:
            # 如果推理太短，可能是默认值，保留它但标记
            pass
    
    # 将AI分析内容存储到状态中
    state["data"]["llm_analysis_content"] = llm_analysis_content

    # 合并预填充的持有决策和 LLM 结果
    # merged 运行时格式: {"NIO": PortfolioDecision(...), "PYPL": PortfolioDecision(...), "BABA": PortfolioDecision(...)}
    merged = dict(prefilled_decisions)
    # 用 LLM 的结果更新合并字典（覆盖预填充的决策）
    merged.update(llm_out.decisions)
    # 返回合并后的决策
    return PortfolioManagerOutput(decisions=merged)

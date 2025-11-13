import sys

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from colorama import Fore, Style, init
import questionary
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.risk_manager import risk_management_agent
from src.graph.state import AgentState
from src.utils.display import print_trading_output
from src.utils.analysts import ANALYST_ORDER, get_analyst_nodes
from src.utils.progress import progress
from src.utils.visualize import save_graph_as_png
from src.cli.input import (
    parse_cli_inputs,
)
from src.data.cache import get_cache
from src.mycount import initial_positions, initial_realized_gains, CountInfo

import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

# Load environment variables from .env file
load_dotenv()

init(autoreset=True)


def parse_hedge_fund_response(response):
    """Parses a JSON string and returns a dictionary."""
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        print(f"JSON解码错误 / JSON decoding error: {e}\n响应 / Response: {repr(response)}")
        return None
    except TypeError as e:
        print(f"无效的响应类型（期望字符串，得到{type(response).__name__}） / Invalid response type (expected string, got {type(response).__name__}): {e}")
        return None
    except Exception as e:
        print(f"解析响应时发生意外错误 / Unexpected error while parsing response: {e}\n响应 / Response: {repr(response)}")
        return None


##### Run the Hedge Fund #####
def run_hedge_fund(
    tickers: list[str],
    start_date: str,
    end_date: str,
    portfolio: dict,
    show_reasoning: bool = False,
    selected_analysts: list[str] = [],
    model_name: str = "gpt-4.1",
    model_provider: str = "OpenAI",
):
    # Start progress tracking
    progress.start()

    try:
        # Build workflow (default to all analysts when none provided)
        workflow = create_workflow(selected_analysts if selected_analysts else None)
        agent = workflow.compile()

        final_state = agent.invoke(
            {
                "messages": [               
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "start_date": start_date,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                },
            },
        )

        return {
            "decisions": parse_hedge_fund_response(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
    finally:
        # Stop progress tracking
        progress.stop()


def start(state: AgentState):
    """Initialize the workflow with the input message."""
    return state


def create_workflow(selected_analysts=None):
    """Create the workflow with selected analysts."""
    workflow = StateGraph(AgentState)
    workflow.add_node("start_node", start)

    # Get analyst nodes from the configuration
    analyst_nodes = get_analyst_nodes()

    # Default to all analysts if none selected
    if selected_analysts is None:
        selected_analysts = list(analyst_nodes.keys())
    # Add selected analyst nodes
    for analyst_key in selected_analysts:
        node_name, node_func = analyst_nodes[analyst_key]
        workflow.add_node(node_name, node_func)
        workflow.add_edge("start_node", node_name)

    # Always add risk and portfolio management
    workflow.add_node("risk_management_agent", risk_management_agent)
    workflow.add_node("portfolio_manager", portfolio_management_agent)

    # Connect selected analysts to risk management
    for analyst_key in selected_analysts:
        node_name = analyst_nodes[analyst_key][0]
        workflow.add_edge(node_name, "risk_management_agent")

    workflow.add_edge("risk_management_agent", "portfolio_manager")
    workflow.add_edge("portfolio_manager", END)

    workflow.set_entry_point("start_node")
    return workflow


if __name__ == "__main__":
    inputs = parse_cli_inputs(
        description="Run the hedge fund trading system",
        require_tickers=True,
        default_months_back=None,
        include_graph_flag=True,
        include_reasoning_flag=True,
    )

    tickers = inputs.tickers
    selected_analysts = inputs.selected_analysts
    
    # 如果使用 --tickers-all，显示使用的 ticker 列表
    if inputs.tickers_all:
        print(f"{Fore.CYAN}使用 --tickers-all 选项，将分析以下所有股票代码 / Using --tickers-all option, will analyze all tickers:{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{', '.join(tickers)}{Style.RESET_ALL}\n")
    
    # 构建投资组合数据结构
    # 这个字典包含了投资组合的所有关键信息，用于跟踪现金、持仓、保证金和已实现收益
    portfolio = {
        # 现金余额：投资组合中可用的现金金额（美元）
        # 用于买入股票或作为保证金
        "cash": CountInfo.initial_cash,
        
        # 保证金要求：做空交易所需的保证金比例（0.0-1.0）
        # 例如：0.5 表示做空需要50%的保证金
        # 用于计算可以做空的最大头寸
        "margin_requirement": CountInfo.margin_requirement,
        
        # 已使用的保证金：当前已用于做空交易的保证金金额（美元）
        # 初始值为0.0，随着做空头寸的增加而增加
        "margin_used": 0.0,
        
        # 持仓信息：每个股票代码的持仓详情
        # 包含多头、空头、成本基础和保证金使用情况
        "positions": {
            ticker: {
                # 多头持仓数量：持有的股票数量（股数）
                # 正数表示持有，0表示无持仓
                "long": initial_positions.get(ticker, {}).get("long", 0),
                
                # 空头持仓数量：做空的股票数量（股数）
                # 正数表示做空数量，0表示无空头
                "short": initial_positions.get(ticker, {}).get("short", 0),
                
                # 多头成本基础：买入多头股票的平均成本（美元）
                # 用于计算盈亏，等于总买入成本 / 持仓数量
                "long_cost_basis": initial_positions.get(ticker, {}).get("long_cost_basis", 0.0),
                
                # 空头成本基础：做空股票的平均价格（美元）
                # 用于计算盈亏，等于总做空价格 / 做空数量
                "short_cost_basis": initial_positions.get(ticker, {}).get("short_cost_basis", 0.0),
                
                # 空头保证金使用：该股票做空头寸占用的保证金金额（美元）
                # 等于做空数量 × 当前价格 × 保证金要求
                # 初始值需要根据初始空头持仓计算
                "short_margin_used": (
                    initial_positions.get(ticker, {}).get("short", 0) *
                    initial_positions.get(ticker, {}).get("short_cost_basis", 0.0) *
                    inputs.margin_requirement
                ),
            }
            for ticker in tickers  # 为每个股票代码初始化持仓结构
        },
        
        # 已实现收益：每个股票代码的已实现盈亏（美元）
        # 当平仓时，盈亏会记录在这里
        "realized_gains": {
            ticker: {
                # 多头已实现收益：平仓多头头寸时实现的盈亏（美元）
                # 正数表示盈利，负数表示亏损
                "long": initial_realized_gains.get(ticker, {}).get("long", 0.0),
                
                # 空头已实现收益：平仓空头头寸时实现的盈亏（美元）
                # 正数表示盈利（做空后价格下跌），负数表示亏损（做空后价格上涨）
                "short": initial_realized_gains.get(ticker, {}).get("short", 0.0),
            }
            for ticker in tickers  # 为每个股票代码初始化已实现收益结构
        },
    }
    
    # 计算初始总保证金使用（所有股票的空头保证金之和）
    portfolio["margin_used"] = sum(
        pos["short_margin_used"] for pos in portfolio["positions"].values()
    )

    print("💥初始数据", portfolio)

    result = run_hedge_fund(
        tickers=tickers,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        portfolio=portfolio,
        show_reasoning=inputs.show_reasoning,
        selected_analysts=inputs.selected_analysts,
        model_name=inputs.model_name,
        model_provider=inputs.model_provider,
    )
    print_trading_output(result, model_name=inputs.model_name, model_provider=inputs.model_provider)
    
    # Display cache statistics
    cache = get_cache()
    cache.print_cache_stats()

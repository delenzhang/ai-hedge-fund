"""
短线新闻分析 Agent 监控脚本

这个脚本定期运行 short_term_news_agent 来分析消息面对当前持仓的影响，
并在检测到重要变化时发送企业微信消息提醒。
"""
import sys
from pathlib import Path
import time
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agents.short_term_news_agent import short_term_news_agent, short_term_news_agent_single_ticker
from src.graph.state import AgentState
from src.mycount import initial_positions, initial_realized_gains, CountInfo
from src.tools.data_api import get_fed_rate_cut_expectation
from src.wexin import send_wechat_message
from src.tools.alert_utils import (
    load_cached_result,
    save_cached_result,
    check_fed_rate_risk,
    detect_significant_changes,
    format_risk_alert_message,
    format_wechat_message,
    format_single_ticker_wechat_message,
    format_action_description,
    format_news_summary,
    get_default_model_config,
    save_operations_history,
    load_operations_history,
)
import json

# 加载环境变量
load_dotenv()

# 上一次分析结果的缓存文件路径
CACHE_DIR = project_root / ".cache" / "short_term_news"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "alert.json"
HISTORY_FILE = CACHE_DIR / "operations_history.json"

# 获取默认模型配置
DEFAULT_MODEL_NAME, DEFAULT_MODEL_PROVIDER = get_default_model_config(project_root)


def run_analysis():
    """运行一次分析（逐个股票分析版本）"""
    # 从 mycount.py 获取持仓信息
    positions = initial_positions
    tickers = list(positions.keys())
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始分析...")
    print(f"当前持仓股票: {', '.join(tickers)}")
    print(f"使用模型: {DEFAULT_MODEL_NAME} ({DEFAULT_MODEL_PROVIDER})")
    print(f"分析模式: 逐个股票分析，分析完立即发送")
    
    # 创建初始状态（每个股票共享同一个state）
    state: AgentState = {
        "messages": [
            HumanMessage(
                content="分析消息面对当前持仓的影响，并提供短线交易建议。",
            )
        ],
        "data": {
            "portfolio": {
                "cash": CountInfo.initial_cash,
                "positions": positions,
                "equity": CountInfo.initial_cash,
                "margin_requirement": CountInfo.margin_requirement,
                "margin_used": 0.0,
            },
            "analyst_signals": {},
            "current_prices": {},
        },
        "metadata": {
            "show_reasoning": False,  # 监控模式下不显示详细推理
            "model_name": DEFAULT_MODEL_NAME,  # 使用 api_models.json 中的第一个模型
            "model_provider": DEFAULT_MODEL_PROVIDER,  # 使用 api_models.json 中的第一个模型提供商
        },
    }
    
    # 用于保存所有股票的结果
    all_decisions = {}
    all_fed_expectation = {}
    all_filtered_news = {}
    all_technical_analysis = {}
    all_price_trend_analysis = {}
    
    # 加载上一次的分析结果（用于检测变化）
    last_result = load_cached_result(CACHE_FILE)
    
    # 用于统计
    success_count = 0
    skip_count = 0
    
    try:
        # 逐个股票进行分析
        for idx, ticker in enumerate(tickers, 1):
            print(f"\n{'='*80}")
            print(f"正在分析第 {idx}/{len(tickers)} 个股票: {ticker}")
            print(f"{'='*80}")
            
            try:
                # 调用单个股票分析 Agent
                result = short_term_news_agent_single_ticker(ticker, state, agent_id="short_term_news_agent")
        
                # 提取结果
                decision = result["decision"]
                confidence = decision.confidence
                
                # 保存到全局结果中
                all_decisions[ticker] = decision.model_dump()
                all_fed_expectation = result["fed_expectation"]  # 所有股票共享同一个降息预期
                all_filtered_news[ticker] = result["ticker_news"]
                all_technical_analysis[ticker] = result["ticker_technical"]
                all_price_trend_analysis[ticker] = result["ticker_price_trend"]
                
                # 过滤决策：只保留信心度超过70%的决策
                if confidence <= 70:
                    skip_count += 1
                    print(f"\n❌ [{ticker}] 跳过：信心度 {confidence}% <= 70%")
                    print(f"  操作: {decision.action}")
                    print(f"  数量: {decision.quantity}")
                    if decision.suggested_price:
                        print(f"  建议价格: ${decision.suggested_price:.2f}")
                    if decision.time_window:
                        print(f"  时间窗口: {decision.time_window}")
                    if decision.reasoning:
                        reasoning_short = decision.reasoning[:200] + "..." if len(decision.reasoning) > 200 else decision.reasoning
                        print(f"  推理: {reasoning_short}")
                    continue
                
                # 信心度足够，准备发送企业微信消息
                success_count += 1
                print(f"\n✅ [{ticker}] 信心度 {confidence}% > 70%，准备发送企业微信消息")
                
                # 保存该股票的操作到历史记录
                save_operations_history({ticker: decision.model_dump()}, HISTORY_FILE)
                
                # 检测该股票的变化
                ticker_last_decision = None
                if last_result:
                    last_decisions = last_result.get("decisions", {})
                    ticker_last_decision = last_decisions.get(ticker)
                
                # 构建变化描述
                ticker_specific_changes = ""
                if ticker_last_decision:
                    last_action = ticker_last_decision.get("action", "hold")
                    current_action = decision.action
                    if last_action != current_action:
                        ticker_specific_changes = f"{ticker} 操作变化: {last_action} → {current_action}"
                
                # 立即发送企业微信消息
                wechat_message = format_single_ticker_wechat_message(
                    ticker=ticker,
                    decision=decision.model_dump(),
                    filtered_news_by_ticker={ticker: result["ticker_news"]},
                    fed_expectation=result["fed_expectation"],
                    changes_desc=ticker_specific_changes,
                    technical_analysis=result["ticker_technical"],
                    price_trend_analysis=result["ticker_price_trend"],
                )
                send_wechat_message(wechat_message)
                print(f"✅ [{ticker}] 企业微信消息已发送")
                
                # 添加短暂延迟，避免消息发送过快
                if idx < len(tickers):  # 不是最后一个股票
                    print(f"等待 1 秒后继续...")
                    time.sleep(1)
                
            except Exception as e:
                print(f"\n❌ [{ticker}] 分析失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 分析结束，输出统计信息
        print(f"\n{'='*80}")
        print(f"分析完成！")
        print(f"总共分析: {len(tickers)} 只股票")
        print(f"成功发送: {success_count} 条消息")
        print(f"跳过（信心度不足）: {skip_count} 只股票")
        print(f"{'='*80}")
        
        # 保存当前结果到缓存（用于下次对比）
        if all_decisions:
            result_dict = {
                "decisions": all_decisions,
                "fed_expectation": all_fed_expectation,
                "filtered_news_by_ticker": all_filtered_news,
                "technical_analysis": all_technical_analysis,
                "price_trend_analysis": all_price_trend_analysis,
            }
            save_cached_result(result_dict, CACHE_FILE)
            print("分析结果已保存到缓存")
        
    except Exception as e:
        print(f"运行异常: {e}")
        import traceback
        traceback.print_exc()


def run_scheduled(interval_minutes: int = 720):
    """
    定时运行分析，每指定分钟执行一次
    
    参数:
        interval_minutes: 执行间隔（分钟），默认720分钟（12小时）
    """
    print(f"开始定时监控，每 {interval_minutes} 分钟执行一次")
    print("按 Ctrl+C 停止")
    
    while True:
        try:
            run_analysis()
            next_run_time = datetime.now().replace(microsecond=0) + timedelta(minutes=interval_minutes)
            print(f"\n下次执行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"等待 {interval_minutes} 分钟后进行下次分析...\n")
            time.sleep(interval_minutes * 60)
        except KeyboardInterrupt:
            print("\n监控已停止")
            break
        except Exception as e:
            print(f"运行异常: {e}")
            import traceback
            traceback.print_exc()
            print("异常后等待1分钟再继续...")
            time.sleep(60)  # 异常后等待1分钟再继续


def main():
    """主函数，支持单次运行或循环运行"""
    import argparse
    
    parser = argparse.ArgumentParser(description="短线新闻分析 Agent 监控脚本")
    parser.add_argument(
        "--interval",
        type=int,
        default=720,
        help="循环运行间隔（分钟），0表示只运行一次，默认720分钟（12小时）"
    )
    args = parser.parse_args()
    
    if args.interval > 0:
        # 循环运行模式
        run_scheduled(args.interval)
    else:
        # 单次运行模式
        run_analysis()


if __name__ == "__main__":
    main()

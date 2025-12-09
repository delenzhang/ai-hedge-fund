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
from src.agents.short_term_news_agent import short_term_news_agent
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
    """运行一次分析"""
    # 从 mycount.py 获取持仓信息
    positions = initial_positions
    tickers = list(positions.keys())
    
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始分析...")
    print(f"当前持仓股票: {', '.join(tickers)}")
    print(f"使用模型: {DEFAULT_MODEL_NAME} ({DEFAULT_MODEL_PROVIDER})")
    
    # 创建初始状态
    state: AgentState = {
        "messages": [
            HumanMessage(
                content="分析消息面对当前持仓的影响，并提供短线交易建议。",
            )
        ],
        "data": {
            "tickers": tickers,
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
    
    try:
        # 调用 Agent
        result_state = short_term_news_agent(state, agent_id="short_term_news_agent")
        
        # 解析结果
        last_message = result_state["messages"][-1]
        content = last_message.content
        
        try:
            result_dict = json.loads(content)
            
            # 获取降息预期数据
            fed_expectation = result_state["data"].get("fed_rate_cut_expectation", {})
            result_dict["fed_expectation"] = fed_expectation
            
            # 获取筛选后的新闻数据
            filtered_news_by_ticker = result_state["data"].get("filtered_news_by_ticker", {})
            result_dict["filtered_news_by_ticker"] = filtered_news_by_ticker
            
            # 过滤决策：只保留信心度超过75%的决策
            filtered_decisions = {}
            skipped_decisions = []  # 保存被跳过的决策信息
            skipped_count = 0
            for ticker, decision in result_dict.get("decisions", {}).items():
                confidence = decision.get("confidence", 0)
                if confidence > 70:
                    filtered_decisions[ticker] = decision
                else:
                    skipped_count += 1
                    # 保存被跳过决策的详细信息
                    action = decision.get("action", "unknown")
                    quantity = decision.get("quantity", 0)
                    reasoning = decision.get("reasoning", "")
                    suggested_price = decision.get("suggested_price")
                    time_window = decision.get("time_window", "")
                    skipped_decisions.append({
                        "ticker": ticker,
                        "confidence": confidence,
                        "action": action,
                        "quantity": quantity,
                        "reasoning": reasoning,
                        "suggested_price": suggested_price,
                        "time_window": time_window
                    })
                    # 显示被跳过决策的详细信息
                    print(f"\n跳过 {ticker}：信心度 {confidence}% <= 75%")
                    print(f"  操作: {action}")
                    print(f"  数量: {quantity}")
                    if suggested_price:
                        print(f"  建议价格: {suggested_price}")
                    if time_window:
                        print(f"  时间窗口: {time_window}")
                    if reasoning:
                        # 如果推理内容较长，只显示前200个字符
                        reasoning_short = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
                        print(f"  推理: {reasoning_short}")
                    # 显示相关新闻信息
                    ticker_news = filtered_news_by_ticker.get(ticker, [])
                    if ticker_news:
                        news_summary = format_news_summary(ticker_news, max_items=3)  # 最多显示3条新闻
                        if news_summary:
                            print(f"  相关新闻:")
                            for news_line in news_summary.split("\n"):
                                print(f"  {news_line}")
            
            if skipped_count > 0:
                print(f"\n共跳过 {skipped_count} 个低信心度决策（信心度 <= 75%）")
            
            # 即使没有高信心度决策，也要发送企业微信信息
            if not filtered_decisions:
                print("警告: 没有信心度超过75%的决策")
                if skipped_count > 0:
                    # 发送跳过决策的企业微信信息
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # 先说结论
                    conclusion = f"⚠️ 所有决策信心度不足，已跳过（共 {skipped_count} 个决策）"
                    
                    # 再说原因：列出被跳过的决策详情
                    skipped_details = []
                    # 获取新闻数据
                    filtered_news_by_ticker = result_dict.get("filtered_news_by_ticker", {})
                    
                    for skipped in skipped_decisions:
                        ticker = skipped["ticker"]
                        confidence = skipped["confidence"]
                        action = skipped["action"]
                        quantity = skipped["quantity"]
                        reasoning = skipped.get("reasoning", "")
                        suggested_price = skipped.get("suggested_price")
                        time_window = skipped.get("time_window", "")
                        
                        action_emoji = {
                            "buy": "📈",
                            "sell": "📉",
                            "short": "🔻",
                            "cover": "🔺",
                            "hold": "⏸️"
                        }.get(action, "⏸️")
                        
                        action_desc = format_action_description(action, quantity)
                        detail_line = f"{action_emoji} {ticker}: {action_desc} | 信心度 {confidence}%"
                        
                        if suggested_price:
                            detail_line += f" | 建议价格 ${suggested_price:.2f}"
                        if time_window:
                            detail_line += f" | 时间窗口 {time_window}"
                        if reasoning:
                            reasoning_display = reasoning[:150] + "..." if len(reasoning) > 150 else reasoning
                            detail_line += f"\n   💭 原因: {reasoning_display}"
                        
                        # 添加相关新闻信息
                        ticker_news = filtered_news_by_ticker.get(ticker, [])
                        if ticker_news:
                            news_summary = format_news_summary(ticker_news, max_items=3)  # 最多显示3条新闻
                            if news_summary:
                                detail_line += f"\n   📰 相关新闻:\n{news_summary}"
                        
                        skipped_details.append(detail_line)
                    
                    reason = "\n".join(skipped_details)
                    
                    wechat_message = f"""<@delenzhang> 短线新闻分析提醒

⏰ 时间: {timestamp}

{conclusion}

📋 被跳过的决策详情:
{reason}

💡 说明: 所有决策的信心度均未超过75%，为保证交易质量，已全部跳过。建议继续观察市场变化，等待更高信心度的交易信号。
"""
                    send_wechat_message(wechat_message)
                    print("已发送跳过决策的企业微信提醒")
                # 不保存结果，因为没有高信心度决策
                return
            
            # 更新结果字典，只包含高信心度的决策
            result_dict["decisions"] = filtered_decisions
            
            # 保存当前操作到历史记录（只保存高信心度的决策）
            save_operations_history(filtered_decisions, HISTORY_FILE)
            
            # 加载上一次结果
            last_result = load_cached_result(CACHE_FILE)
            
            # 优先检查降息概率的重大变化（超过15%），如果存在，立即发送风险提醒
            has_fed_risk, fed_risk_message = check_fed_rate_risk(result_dict, last_result)
            if has_fed_risk:
                print(f"\n⚠️ 检测到降息概率重大变化，立即发送风险提醒\n")
                # 发送专门的风险管理提醒
                risk_alert_message = format_risk_alert_message(result_dict, fed_risk_message)
                send_wechat_message(risk_alert_message)
                # 保存当前结果
                save_cached_result(result_dict, CACHE_FILE)
                print("风险提醒已发送，分析结果已保存")
                return
            
            # 检测其他变化
            changes_desc, decisions_same = detect_significant_changes(result_dict, last_result)
            
            # 如果消息描述不为空，表示需要发送消息
            if changes_desc:
                if decisions_same and changes_desc == "操作建议与上次相同":
                    print(f"\n✅ 操作建议与上次相同，发送简单提醒\n")
                elif decisions_same:
                    print(f"\n✅ 操作建议与上次相同（但有其他变化），发送简单提醒\n")
                else:
                    print(f"\n🔔 检测到变化:\n{changes_desc}\n")
                
                # 发送企业微信消息（根据决策是否相同选择不同格式）
                wechat_message = format_wechat_message(result_dict, changes_desc, decisions_same)
                send_wechat_message(wechat_message)
                
                # 保存当前结果
                save_cached_result(result_dict, CACHE_FILE)
                print("分析结果已保存")
            else:
                print("未检测到显著变化，且无决策数据，不发送提醒")
                # 即使没有变化，也保存当前结果（用于下次对比）
                save_cached_result(result_dict, CACHE_FILE)
            
        except json.JSONDecodeError as e:
            print(f"解析结果失败: {e}")
            print(f"原始内容: {content[:500]}...")
        
    except Exception as e:
        print(f"分析过程出错: {e}")
        import traceback
        traceback.print_exc()


def run_scheduled(interval_minutes: int = 120):
    """
    定时运行分析，每指定分钟执行一次
    
    参数:
        interval_minutes: 执行间隔（分钟），默认120分钟（2小时）
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
        default=120,
        help="循环运行间隔（分钟），0表示只运行一次，默认120分钟（2小时）"
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


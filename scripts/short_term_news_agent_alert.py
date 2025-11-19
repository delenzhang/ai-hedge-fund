"""
短线新闻分析 Agent 监控脚本

这个脚本定期运行 short_term_news_agent 来分析消息面对当前持仓的影响，
并在检测到重要变化时发送企业微信消息提醒。
"""
import sys
from pathlib import Path
import time
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from src.agents.short_term_news_agent import short_term_news_agent
from src.graph.state import AgentState
from src.mycount import initial_positions, initial_realized_gains, CountInfo
from src.tools.data_api import get_fed_rate_cut_expectation
from src.wexin import send_wechat_message
from src.llm.models import load_models_from_json, ModelProvider
from pathlib import Path
import json

# 加载环境变量
load_dotenv()

# 上一次分析结果的缓存文件路径
CACHE_FILE = Path(".cache/short_term_news_agent_last_result.json")

# 从 api_models.json 加载模型配置，使用第一个模型作为默认
def get_default_model_config():
    """从 api_models.json 获取第一个模型作为默认配置"""
    try:
        models_json_path = project_root / "src" / "llm" / "api_models.json"
        models = load_models_from_json(str(models_json_path))
        if models:
            first_model = models[0]
            return first_model.model_name, first_model.provider.value
    except Exception as e:
        print(f"警告: 无法加载 api_models.json，使用默认配置: {e}")
    
    # 回退到默认配置
    return "gpt-4.1", "OPENAI"

# 获取默认模型配置
DEFAULT_MODEL_NAME, DEFAULT_MODEL_PROVIDER = get_default_model_config()


def load_last_result() -> dict | None:
    """加载上一次的分析结果"""
    if not CACHE_FILE.exists():
        return None
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载上一次结果失败: {e}")
        return None


def save_current_result(result: dict):
    """保存当前的分析结果"""
    try:
        # 确保缓存目录存在
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加时间戳
        result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存当前结果失败: {e}")


def detect_significant_changes(current_result: dict, last_result: dict | None) -> tuple[bool, str]:
    """
    检测是否有显著变化
    
    返回:
        (是否有变化, 变化描述)
    """
    if last_result is None:
        return True, "首次运行，无历史数据对比"
    
    changes = []
    
    # 1. 检查降息概率变化
    current_fed = current_result.get("fed_expectation", {})
    last_fed = last_result.get("fed_expectation", {})
    
    # 只有当两者都不是错误消息时才比较
    if (current_fed and last_fed and 
        "error" not in current_fed and "error" not in last_fed):
        current_total_cut = current_fed.get("total_cut_probability", 0.0)
        last_total_cut = last_fed.get("total_cut_probability", 0.0)
        
        # 降息概率变化超过10%（0.1）
        if abs(current_total_cut - last_total_cut) > 0.1:
            change_pct = (current_total_cut - last_total_cut) * 100
            changes.append(f"降息概率大幅变动: {last_total_cut*100:.1f}% → {current_total_cut*100:.1f}% (变化 {change_pct:+.1f}%)")
    
    # 2. 检查各股票的交易建议变化
    current_decisions = current_result.get("decisions", {})
    last_decisions = last_result.get("decisions", {})
    
    for ticker in current_decisions:
        current_decision = current_decisions.get(ticker, {})
        last_decision = last_decisions.get(ticker, {})
        
        if not last_decision:
            continue
        
        # 检查操作变化
        current_action = current_decision.get("action", "hold")
        last_action = last_decision.get("action", "hold")
        
        if current_action != last_action:
            changes.append(f"{ticker} 操作变化: {last_action} → {current_action}")
        
        # 检查新闻影响评分变化（变化超过10分）
        current_score = current_decision.get("score", {})
        last_score = last_decision.get("score", {})
        
        current_news_impact = current_score.get("news_impact", 0)
        last_news_impact = last_score.get("news_impact", 0)
        
        if abs(current_news_impact - last_news_impact) > 10:
            changes.append(f"{ticker} 新闻影响评分变化: {last_news_impact} → {current_news_impact} (变化 {current_news_impact - last_news_impact:+.0f}分)")
        
        # 检查降息预期影响评分变化（变化超过10分）
        current_fed_impact = current_score.get("fed_impact", 0)
        last_fed_impact = last_score.get("fed_impact", 0)
        
        if abs(current_fed_impact - last_fed_impact) > 10:
            changes.append(f"{ticker} 降息预期影响评分变化: {last_fed_impact} → {current_fed_impact} (变化 {current_fed_impact - last_fed_impact:+.0f}分)")
        
        # 检查总分变化（变化超过15分）
        current_total = current_score.get("total_score", 0)
        last_total = last_score.get("total_score", 0)
        
        if abs(current_total - last_total) > 15:
            changes.append(f"{ticker} 总分变化: {last_total} → {current_total} (变化 {current_total - last_total:+.0f}分)")
    
    if changes:
        return True, "\n".join(changes)
    
    return False, ""


def format_wechat_message(current_result: dict, changes: str) -> str:
    """格式化企业微信消息内容"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取降息预期
    fed_expectation = current_result.get("fed_expectation", {})
    fed_info = ""
    if fed_expectation and "error" not in fed_expectation:
        total_cut = fed_expectation.get("total_cut_probability", 0.0) * 100
        no_change = fed_expectation.get("no_change", 0.0) * 100
        fed_info = f"\n📊 降息预期: 降息 {total_cut:.1f}% | 不变 {no_change:.1f}%"
    
    # 获取交易建议摘要
    decisions = current_result.get("decisions", {})
    decisions_summary = []
    for ticker, decision in decisions.items():
        action = decision.get("action", "hold")
        quantity = decision.get("quantity", 0)
        confidence = decision.get("confidence", 0)
        score = decision.get("score", {})
        total_score = score.get("total_score", 0)
        
        action_emoji = {
            "buy": "📈",
            "sell": "📉",
            "short": "🔻",
            "cover": "🔺",
            "hold": "⏸️"
        }.get(action, "⏸️")
        
        decisions_summary.append(
            f"{action_emoji} {ticker}: {action.upper()} {quantity}股 | 信心度 {confidence}% | 评分 {total_score}/100"
        )
    
    message = f"""<@delenzhang> 短线新闻分析提醒

⏰ 时间: {timestamp}

🔔 检测到重要变化:
{changes}
{fed_info}

📋 当前交易建议:
{chr(10).join(decisions_summary) if decisions_summary else "无交易建议"}

💡 整体评估:
{current_result.get('overall_assessment', '无评估')[:200]}...
"""
    
    return message


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
            
            # 加载上一次结果
            last_result = load_last_result()
            
            # 检测变化
            has_changes, changes_desc = detect_significant_changes(result_dict, last_result)
            
            if has_changes:
                print(f"\n检测到变化:\n{changes_desc}\n")
                
                # 发送企业微信消息
                wechat_message = format_wechat_message(result_dict, changes_desc)
                send_wechat_message(wechat_message)
                
                # 保存当前结果
                save_current_result(result_dict)
                print("分析结果已保存")
            else:
                print("未检测到显著变化，不发送提醒")
                # 即使没有变化，也保存当前结果（用于下次对比）
                save_current_result(result_dict)
            
        except json.JSONDecodeError as e:
            print(f"解析结果失败: {e}")
            print(f"原始内容: {content[:500]}...")
        
    except Exception as e:
        print(f"分析过程出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主函数，支持单次运行或循环运行"""
    import argparse
    
    parser = argparse.ArgumentParser(description="短线新闻分析 Agent 监控脚本")
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="循环运行间隔（分钟），0表示只运行一次（默认：0）"
    )
    args = parser.parse_args()
    
    if args.interval > 0:
        # 循环运行模式
        print(f"开始循环监控，间隔 {args.interval} 分钟")
        print("按 Ctrl+C 停止")
        
        while True:
            try:
                run_analysis()
                print(f"\n等待 {args.interval} 分钟后进行下次分析...\n")
                time.sleep(args.interval * 60)
            except KeyboardInterrupt:
                print("\n监控已停止")
                break
            except Exception as e:
                print(f"运行异常: {e}")
                time.sleep(60)  # 异常后等待1分钟再继续
    else:
        # 单次运行模式
        run_analysis()


if __name__ == "__main__":
    main()


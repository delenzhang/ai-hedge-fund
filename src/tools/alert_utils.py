"""
短线新闻分析提醒工具模块

提供分析结果缓存、变化检测、消息格式化等公共功能
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


def load_cached_result(cache_file: Path) -> dict | None:
    """
    加载缓存的分析结果
    
    参数:
        cache_file: 缓存文件路径
    
    返回:
        缓存的结果字典，如果文件不存在则返回 None
    """
    if not cache_file.exists():
        return None
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载缓存结果失败: {e}")
        return None


def save_cached_result(result: dict, cache_file: Path):
    """
    保存分析结果到缓存文件
    
    参数:
        result: 要保存的结果字典
        cache_file: 缓存文件路径
    """
    try:
        # 确保缓存目录存在
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 添加时间戳
        result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存缓存结果失败: {e}")


def check_fed_rate_risk(current_result: dict, last_result: dict | None, threshold: float = 0.15) -> tuple[bool, str]:
    """
    检查降息概率的重大变化，如果变化超过阈值，返回风险提醒
    
    参数:
        current_result: 当前分析结果
        last_result: 上一次分析结果
        threshold: 变化阈值，默认 0.15 (15%)
    
    返回:
        (是否有重大风险, 风险提醒消息)
    """
    if last_result is None:
        return False, ""
    
    current_fed = current_result.get("fed_expectation", {})
    last_fed = last_result.get("fed_expectation", {})
    
    # 只有当两者都不是错误消息时才比较
    if (current_fed and last_fed and 
        "error" not in current_fed and "error" not in last_fed):
        current_total_cut = current_fed.get("total_cut_probability", 0.0)
        last_total_cut = last_fed.get("total_cut_probability", 0.0)
        change_abs = abs(current_total_cut - last_total_cut)
        change_pct = (current_total_cut - last_total_cut) * 100
        
        # 降息概率变化超过阈值 - 重大变化，需要立即风险管理
        if change_abs > threshold:
            if current_total_cut > last_total_cut:
                risk_level = "⚠️ 高风险"
                risk_action = "降息概率大幅上升，看涨持仓利好，看跌持仓需减仓或平仓"
            else:
                risk_level = "🔴 极高风险"
                risk_action = "降息概率大幅下降，看涨持仓需立即减仓或止损，看跌持仓可考虑加仓"
            
            risk_message = f"""{risk_level} 降息概率重大变动

📊 变化详情:
  之前: {last_total_cut*100:.1f}%
  现在: {current_total_cut*100:.1f}%
  变化: {change_pct:+.1f}%

🚨 风险管理建议:
  {risk_action}

💡 建议操作:
  - 立即检查所有持仓的风险敞口
  - 根据降息概率变化调整仓位
  - 考虑设置止损或止盈点
  - 密切关注市场后续反应
"""
            return True, risk_message
    
    return False, ""


def detect_significant_changes(
    current_result: dict, 
    last_result: dict | None,
    fed_threshold: float = 0.1,
    score_threshold: int = 10,
    total_score_threshold: int = 15
) -> tuple[str, bool]:
    """
    检测是否有显著变化，并判断是否需要发送消息
    
    参数:
        current_result: 当前分析结果
        last_result: 上一次分析结果
        fed_threshold: 降息概率变化阈值，默认 0.1 (10%)
        score_threshold: 评分变化阈值，默认 10 分
        total_score_threshold: 总分变化阈值，默认 15 分
    
    返回:
        (消息描述, 决策是否相同)
        - 如果消息描述为空字符串，表示不需要发送消息
        - 如果消息描述不为空，表示需要发送消息（可能是变化，也可能是"操作建议与上次相同"）
    """
    if last_result is None:
        return "首次运行，无历史数据对比", False
    
    changes = []
    decisions_same = True  # 标记决策是否相同
    
    # 1. 检查降息概率变化（最重要，优先检查）
    current_fed = current_result.get("fed_expectation", {})
    last_fed = last_result.get("fed_expectation", {})
    
    # 只有当两者都不是错误消息时才比较
    if (current_fed and last_fed and 
        "error" not in current_fed and "error" not in last_fed):
        current_total_cut = current_fed.get("total_cut_probability", 0.0)
        last_total_cut = last_fed.get("total_cut_probability", 0.0)
        change_abs = abs(current_total_cut - last_total_cut)
        change_pct = (current_total_cut - last_total_cut) * 100
        
        # 降息概率变化超过15%（0.15）- 重大变化，需要立即风险管理
        if change_abs > 0.15:
            if current_total_cut > last_total_cut:
                risk_level = "⚠️ 高风险"
                risk_action = "降息概率大幅上升，看涨持仓利好，看跌持仓需减仓或平仓"
            else:
                risk_level = "🔴 极高风险"
                risk_action = "降息概率大幅下降，看涨持仓需立即减仓或止损，看跌持仓可考虑加仓"
            changes.append(f"{risk_level} 降息概率重大变动: {last_total_cut*100:.1f}% → {current_total_cut*100:.1f}% (变化 {change_pct:+.1f}%)")
            changes.append(f"风险管理建议: {risk_action}")
        # 降息概率变化超过阈值 - 显著变化
        elif change_abs > fed_threshold:
            changes.append(f"降息概率大幅变动: {last_total_cut*100:.1f}% → {current_total_cut*100:.1f}% (变化 {change_pct:+.1f}%)")
    
    # 2. 检查各股票的交易建议变化
    current_decisions = current_result.get("decisions", {})
    last_decisions = last_result.get("decisions", {})
    
    # 检查是否有新增或删除的股票
    current_tickers = set(current_decisions.keys())
    last_tickers = set(last_decisions.keys())
    
    if current_tickers != last_tickers:
        # 有新增或删除的股票，决策不同
        decisions_same = False
        if current_tickers - last_tickers:
            changes.append(f"新增股票: {', '.join(current_tickers - last_tickers)}")
        if last_tickers - current_tickers:
            changes.append(f"移除股票: {', '.join(last_tickers - current_tickers)}")
    
    for ticker in current_decisions:
        current_decision = current_decisions.get(ticker, {})
        last_decision = last_decisions.get(ticker, {})
        
        if not last_decision:
            # 新增的股票，决策不同
            decisions_same = False
            continue
        
        # 检查操作变化
        current_action = current_decision.get("action", "hold")
        last_action = last_decision.get("action", "hold")
        
        if current_action != last_action:
            changes.append(f"{ticker} 操作变化: {last_action} → {current_action}")
            decisions_same = False
        
        # 检查评分变化
        current_score = current_decision.get("score", {})
        last_score = last_decision.get("score", {})
        
        # 检查新闻影响评分变化
        current_news_impact = current_score.get("news_impact", 0)
        last_news_impact = last_score.get("news_impact", 0)
        
        if abs(current_news_impact - last_news_impact) > score_threshold:
            changes.append(f"{ticker} 新闻影响评分变化: {last_news_impact} → {current_news_impact} (变化 {current_news_impact - last_news_impact:+.0f}分)")
        
        # 检查降息预期影响评分变化
        current_fed_impact = current_score.get("fed_impact", 0)
        last_fed_impact = last_score.get("fed_impact", 0)
        
        if abs(current_fed_impact - last_fed_impact) > score_threshold:
            changes.append(f"{ticker} 降息预期影响评分变化: {last_fed_impact} → {current_fed_impact} (变化 {current_fed_impact - last_fed_impact:+.0f}分)")
        
        # 检查总分变化
        current_total = current_score.get("total_score", 0)
        last_total = last_score.get("total_score", 0)
        
        if abs(current_total - last_total) > total_score_threshold:
            changes.append(f"{ticker} 总分变化: {last_total} → {current_total} (变化 {current_total - last_total:+.0f}分)")
    
    # 如果有变化，返回变化信息
    if changes:
        return "\n".join(changes), decisions_same
    
    # 检查操作是否完全相同（即使股票集合不同，只要共同股票的操作相同，也算相同）
    operations_same = True
    if current_decisions and last_decisions:
        common_tickers = current_tickers & last_tickers
        if common_tickers:
            # 检查共同股票的操作是否相同
            for ticker in common_tickers:
                current_action = current_decisions.get(ticker, {}).get("action", "hold")
                last_action = last_decisions.get(ticker, {}).get("action", "hold")
                if current_action != last_action:
                    operations_same = False
                    break
        # 如果没有共同股票，但decisions_same为True（说明在遍历时没有检测到操作变化），视为相同
        # 这种情况可能是因为股票集合完全不同的原因，但操作逻辑相同
    elif not current_decisions and not last_decisions:
        # 两者都没有决策，视为相同
        operations_same = True
    else:
        # 一个有决策一个没有，视为不同
        operations_same = False
    
    # 如果没有其他变化（changes为空），且有决策数据，应该发送提醒
    # 这样可以确保即使决策保持不变，用户也能收到通知
    if current_decisions:
        # 如果操作相同（基于共同股票比较），或者decisions_same为True（没有检测到操作变化）
        if operations_same or decisions_same:
            return "操作建议与上次相同", True
    
    # 完全没有变化且没有决策数据，不发送提醒
    return "", decisions_same


def format_news_summary(news_list: list[dict], max_items: int = None) -> str:
    """
    格式化新闻摘要，用于消息显示
    
    参数:
        news_list: 新闻列表
        max_items: 最多显示几条新闻，None 表示显示所有新闻
    
    返回:
        格式化的新闻摘要字符串
    """
    if not news_list:
        return ""
    
    # 过滤出近一周的新闻
    cutoff_date = datetime.now() - timedelta(days=7)
    recent_news = []
    
    for news in news_list:
        try:
            # 解析新闻日期时间
            news_datetime_str = news.get("datetime", "")
            if not news_datetime_str:
                continue
            
            # 解析日期时间字符串，格式: "2025-11-19 15:38"
            news_datetime = datetime.strptime(news_datetime_str, "%Y-%m-%d %H:%M")
            
            # 只保留近一周的新闻
            if news_datetime >= cutoff_date:
                recent_news.append(news)
        except (ValueError, TypeError):
            # 如果时间格式不正确，跳过这条新闻
            continue
    
    if not recent_news:
        return ""
    
    # 如果 max_items 为 None，显示所有近一周的新闻
    display_news = recent_news if max_items is None else recent_news[:max_items]
    
    news_items = []
    for news in display_news:
        title_cn = news.get("title_cn", "")
        title = news.get("title", "")
        # 优先使用中文标题，如果没有则使用英文标题
        display_title = title_cn if title_cn else title
        # 限制标题长度，避免消息过长
        if len(display_title) > 80:
            display_title = display_title[:80] + "..."
        
        # 获取时间和来源
        news_datetime_str = news.get("datetime", "")
        source = news.get("source", "")
        url = news.get("url", "")
        
        # 格式化时间显示（只显示日期和时间，不显示秒）
        time_display = ""
        if news_datetime_str:
            try:
                news_dt = datetime.strptime(news_datetime_str, "%Y-%m-%d %H:%M")
                time_display = news_dt.strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                time_display = news_datetime_str
        
        # 格式化来源显示
        source_display = ""
        if source:
            source_display = f" | 来源: {source}"
        elif url:
            # 如果没有 source 字段，尝试从 URL 提取来源
            if "financialjuice" in url.lower():
                source_display = " | 来源: financialjuice"
            elif "truthsocial" in url.lower():
                source_display = " | 来源: truthsocial"
        
        # 构建新闻项
        news_item = f"  • {display_title}"
        if time_display:
            news_item += f" ({time_display})"
        if source_display:
            news_item += source_display
        
        news_items.append(news_item)
    
    return "\n".join(news_items)


def format_action_description(action: str, quantity: int) -> str:
    """
    格式化操作描述，使其更清晰易懂
    
    参数:
        action: 操作类型 (buy, sell, hold, short, cover)
        quantity: 数量
    
    返回:
        格式化的操作描述
    """
    if action == "buy" and quantity > 0:
        return f"买入 {quantity}股"
    elif action == "sell" and quantity > 0:
        return f"卖出 {quantity}股"
    elif action == "short" and quantity > 0:
        return f"做空 {quantity}股"
    elif action == "cover" and quantity > 0:
        return f"平仓 {quantity}股"
    else:
        return "不动"


def format_confidence_explanation(confidence: int) -> str:
    """
    格式化信心度说明，告诉用户多少可以相信，多少可以不管
    
    参数:
        confidence: 信心度 (0-100)
    
    返回:
        信心度说明字符串
    """
    if confidence >= 80:
        return f"信心度 {confidence}%：高度可信，建议重点关注并执行"
    elif confidence >= 60:
        return f"信心度 {confidence}%：中等可信，建议参考但需结合其他因素"
    elif confidence >= 40:
        return f"信心度 {confidence}%：低度可信，仅供参考，不建议作为主要决策依据"
    else:
        return f"信心度 {confidence}%：极低可信，建议忽略或仅作为辅助参考"


def format_risk_alert_message(current_result: dict, risk_message: str) -> str:
    """
    格式化风险管理提醒消息内容
    
    参数:
        current_result: 当前分析结果
        risk_message: 风险提醒消息
    
    返回:
        格式化后的消息字符串
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取降息预期详情
    fed_expectation = current_result.get("fed_expectation", {})
    fed_details = ""
    if fed_expectation and "error" not in fed_expectation:
        total_cut = fed_expectation.get("total_cut_probability", 0.0) * 100
        cut_25bp = fed_expectation.get("cut_25bp", 0.0) * 100
        cut_50bp = fed_expectation.get("cut_50bp_or_more", 0.0) * 100
        no_change = fed_expectation.get("no_change", 0.0) * 100
        hike = fed_expectation.get("hike", 0.0) * 100
        fed_details = f"""
📊 当前降息预期详情:
  - 降息25bp: {cut_25bp:.1f}%
  - 降息50bp+: {cut_50bp:.1f}%
  - 总降息概率: {total_cut:.1f}%
  - 不变: {no_change:.1f}%
  - 加息: {hike:.1f}%"""
    
    # 获取当前持仓摘要和新闻
    positions = current_result.get("decisions", {})
    filtered_news_by_ticker = current_result.get("filtered_news_by_ticker", {})
    positions_summary = []
    for ticker, decision in positions.items():
        action = decision.get("action", "hold")
        quantity = decision.get("quantity", 0)
        confidence = decision.get("confidence", 0)
        reasoning = decision.get("reasoning", "")
        score = decision.get("score", {})
        
        # 获取评分详情
        fed_impact = score.get("fed_impact", 0)
        news_impact = score.get("news_impact", 0)
        position_analysis = score.get("position_analysis", 0)
        total_score = score.get("total_score", 0)
        
        action_emoji = {
            "buy": "📈",
            "sell": "📉",
            "short": "🔻",
            "cover": "🔺",
            "hold": "⏸️"
        }.get(action, "⏸️")
        
        action_desc = format_action_description(action, quantity)
        confidence_explanation = format_confidence_explanation(confidence)
        
        # 获取其他字段
        suggested_price = decision.get("suggested_price")
        time_window = decision.get("time_window", "")
        
        # 构建基础摘要行
        summary_line = f"{action_emoji} {ticker}: {action_desc} | 信心度 {confidence}% | 总分 {total_score}/100"
        
        # 添加评分详情（言简意赅）
        score_details = f"评分: 降息影响{fed_impact}/50 | 新闻影响{news_impact}/50 | 持仓分析{position_analysis}/50"
        summary_line += f"\n{score_details}"
        
        # 添加建议价格和时间窗口（如果有）
        if suggested_price:
            summary_line += f"\n💵 建议价格: ${suggested_price:.2f}"
        if time_window:
            summary_line += f"\n⏱️ 时间窗口: {time_window}"
        
        # 添加原因（如果有）
        if reasoning:
            # 限制原因长度，避免消息过长
            reasoning_display = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            summary_line += f"\n💭 原因：{reasoning_display}"
        
        # 添加信心度说明
        summary_line += f"\n{confidence_explanation}"
        
        # 添加相关新闻（显示所有新闻）
        ticker_news = filtered_news_by_ticker.get(ticker, [])
        if ticker_news:
            news_summary = format_news_summary(ticker_news, max_items=None)
            if news_summary:
                summary_line += f"\n📰 相关新闻:\n{news_summary}"
        
        positions_summary.append(summary_line)
    
    message = f"""<@delenzhang> 🚨 降息概率重大变化 - 风险管理提醒

⏰ 时间: {timestamp}

{risk_message}
{fed_details}

📋 当前持仓建议:
{chr(10).join(positions_summary) if positions_summary else "无持仓建议"}

⚠️ 请立即检查持仓风险，根据降息概率变化调整交易策略！
"""
    
    return message


def format_wechat_message(current_result: dict, changes: str, decisions_same: bool = False) -> str:
    """
    格式化企业微信消息内容
    
    参数:
        current_result: 当前分析结果
        changes: 变化描述
        decisions_same: 决策是否与上次相同，如果相同则发送简单消息
    
    返回:
        格式化后的消息字符串
    """
    # 如果决策相同，发送简单消息
    if decisions_same:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        decisions = current_result.get("decisions", {})
        
        # 构建简单的决策摘要
        decisions_summary = []
        for ticker, decision in decisions.items():
            action = decision.get("action", "hold")
            quantity = decision.get("quantity", 0)
            confidence = decision.get("confidence", 0)
            
            action_emoji = {
                "buy": "📈",
                "sell": "📉",
                "short": "🔻",
                "cover": "🔺",
                "hold": "⏸️"
            }.get(action, "⏸️")
            
            action_desc = format_action_description(action, quantity)
            decisions_summary.append(f"{action_emoji} {ticker}: {action_desc} (信心度 {confidence}%)")
        
        message = f"""<@delenzhang> 短线新闻分析提醒

⏰ 时间: {timestamp}

✅ 操作建议与上次相同

📋 当前交易建议:
{chr(10).join(decisions_summary) if decisions_summary else "无交易建议"}

💡 说明: 本次分析与上次分析的操作建议相同，无需调整持仓。
"""
        return message
    
    # 决策有变化，发送详细消息
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取降息预期
    fed_expectation = current_result.get("fed_expectation", {})
    fed_info = ""
    if fed_expectation and "error" not in fed_expectation:
        total_cut = fed_expectation.get("total_cut_probability", 0.0) * 100
        no_change = fed_expectation.get("no_change", 0.0) * 100
        fed_info = f"\n📊 降息预期: 降息 {total_cut:.1f}% | 不变 {no_change:.1f}%"
    
    # 获取交易建议摘要和新闻
    decisions = current_result.get("decisions", {})
    filtered_news_by_ticker = current_result.get("filtered_news_by_ticker", {})
    decisions_summary = []
    for ticker, decision in decisions.items():
        action = decision.get("action", "hold")
        quantity = decision.get("quantity", 0)
        confidence = decision.get("confidence", 0)
        reasoning = decision.get("reasoning", "")
        score = decision.get("score", {})
        
        # 获取评分详情
        fed_impact = score.get("fed_impact", 0)
        news_impact = score.get("news_impact", 0)
        position_analysis = score.get("position_analysis", 0)
        total_score = score.get("total_score", 0)
        
        action_emoji = {
            "buy": "📈",
            "sell": "📉",
            "short": "🔻",
            "cover": "🔺",
            "hold": "⏸️"
        }.get(action, "⏸️")
        
        action_desc = format_action_description(action, quantity)
        confidence_explanation = format_confidence_explanation(confidence)
        
        # 获取其他字段
        suggested_price = decision.get("suggested_price")
        time_window = decision.get("time_window", "")
        
        # 构建基础摘要行
        summary_line = f"{action_emoji} {ticker}: {action_desc} | 信心度 {confidence}% | 总分 {total_score}/100"
        
        # 添加评分详情（言简意赅）
        score_details = f"评分: 降息影响{fed_impact}/50 | 新闻影响{news_impact}/50 | 持仓分析{position_analysis}/50"
        summary_line += f"\n{score_details}"
        
        # 添加建议价格和时间窗口（如果有）
        if suggested_price:
            summary_line += f"\n💵 建议价格: ${suggested_price:.2f}"
        if time_window:
            summary_line += f"\n⏱️ 时间窗口: {time_window}"
        
        # 添加原因（如果有）
        if reasoning:
            # 限制原因长度，避免消息过长
            reasoning_display = reasoning
            summary_line += f"\n💭 原因：{reasoning_display}"
        
        # 添加信心度说明
        summary_line += f"\n{confidence_explanation}"
        
        # 添加相关新闻（显示所有新闻）
        ticker_news = filtered_news_by_ticker.get(ticker, [])
        if ticker_news:
            news_summary = format_news_summary(ticker_news, max_items=None)
            if news_summary:
                summary_line += f"\n📰 相关新闻:\n{news_summary}"
        
        decisions_summary.append(summary_line)
    
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


def format_technical_analysis_for_wechat(technical_analysis: dict) -> str:
    """
    格式化技术分析信息用于企业微信消息（简洁版）
    
    参数:
        technical_analysis: 单个股票的技术分析结果
    
    返回:
        格式化后的技术分析字符串
    """
    if not technical_analysis:
        return "无技术分析数据"
    
    lines = []
    
    # 综合信号
    signal = technical_analysis.get("signal", "neutral")
    confidence = technical_analysis.get("confidence", 0)
    
    signal_emoji = {
        "bullish": "📈",
        "bearish": "📉",
        "neutral": "➖"
    }.get(signal, "➖")
    
    signal_text = {
        "bullish": "看涨",
        "bearish": "看跌",
        "neutral": "中性"
    }.get(signal, "中性")
    
    lines.append(f"{signal_emoji} 综合信号: {signal_text} (信心度 {confidence}%)")
    
    # 详细分析
    reasoning = technical_analysis.get("reasoning", {})
    if reasoning:
        # 趋势跟踪
        if "trend_following" in reasoning:
            tf = reasoning["trend_following"]
            tf_signal = tf.get("signal", "neutral")
            tf_conf = tf.get("confidence", 0)
            lines.append(f"  • 趋势跟踪: {tf_signal} ({tf_conf}%)")
        
        # 日线分析
        if "daily_kline_analysis" in reasoning:
            daily = reasoning["daily_kline_analysis"]
            strategy = daily.get("strategy", "neutral")
            trend_type = daily.get("trend_type", "unknown")
            trend_strength = daily.get("trend_strength", 0)
            lines.append(f"  • 日线趋势: {strategy} | {trend_type} | 强度{trend_strength}")
        
        # 小时线分析
        if "hourly_kline_analysis" in reasoning:
            hourly = reasoning["hourly_kline_analysis"]
            tactical_signal = hourly.get("tactical_signal", "wait")
            entry_point = hourly.get("entry_point_detected", False)
            entry_text = "是" if entry_point else "否"
            lines.append(f"  • 小时线战术: {tactical_signal} | 买入点: {entry_text}")
    
    return "\n".join(lines)


def format_volume_price_analysis_for_wechat(price_trend: dict) -> str:
    """
    格式化量价关系分析信息用于企业微信消息（详细版，包含量价理论解释）
    
    参数:
        price_trend: 单个股票的价格走势和量价关系分析结果
    
    返回:
        格式化后的量价关系分析字符串
    """
    if not price_trend or "error" in price_trend:
        return "无量价数据"
    
    lines = []
    
    # 当前价格和趋势
    current_price = price_trend.get("current_price", 0)
    trend_5d = price_trend.get("trend_5d", "unknown")
    price_changes = price_trend.get("price_changes", {})
    change_5d = price_changes.get("5d", 0)
    
    lines.append(f"💰 当前价格: ${current_price:.2f}")
    lines.append(f"📊 5日趋势: {trend_5d} ({change_5d:+.2f}%)")
    
    # 量价关系核心信息
    vp_relation = price_trend.get("volume_price_relation", "unknown")
    vp_correlation = price_trend.get("volume_price_correlation", 0)
    
    lines.append(f"")
    lines.append(f"📈 量价关系: {vp_relation}")
    lines.append(f"   相关系数: {vp_correlation:.3f}")
    
    # 量价统计详情（核心量价理论）
    vp_stats = price_trend.get("volume_price_stats", {})
    price_up_vol_up = vp_stats.get("price_up_volume_up", 0)
    price_down_vol_down = vp_stats.get("price_down_volume_down", 0)
    price_up_vol_down = vp_stats.get("price_up_volume_down", 0)
    price_down_vol_up = vp_stats.get("price_down_volume_up", 0)
    
    lines.append(f"")
    lines.append(f"📊 量价配合统计 (近5根K线):")
    
    # 健康的量价关系
    if price_up_vol_up > 0:
        lines.append(f"   ✅ 价涨量增: {price_up_vol_up}次")
        lines.append(f"      → 上涨有资金支持，健康上涨信号")
    
    if price_down_vol_down > 0:
        lines.append(f"   ✅ 价跌量缩: {price_down_vol_down}次")
        lines.append(f"      → 下跌抛压不重，可能是正常回调")
    
    # 背离的量价关系（警示）
    if price_up_vol_down > 0:
        lines.append(f"   ⚠️ 价涨量缩: {price_up_vol_down}次")
        lines.append(f"      → 上涨乏力，缺乏资金支持，可能见顶")
    
    if price_down_vol_up > 0:
        lines.append(f"   ⚠️ 价跌量增: {price_down_vol_up}次")
        lines.append(f"      → 大量抛压，可能加速下跌")
    
    # 放量分析（重要信号）
    volume_surge = price_trend.get("volume_surge_analysis", {})
    if volume_surge.get("is_volume_surge", False):
        lines.append(f"")
        lines.append(f"🔥 放量检测: 已检测到放量")
        
        surge_types = volume_surge.get("surge_type", [])
        bullish_prob = volume_surge.get("bullish_probability", 0)
        
        if surge_types:
            lines.append(f"   类型: {', '.join(surge_types)}")
        
        if bullish_prob > 0:
            lines.append(f"   看涨概率: {bullish_prob}%")
        
        # 详细说明不同放量类型的含义
        if volume_surge.get("is_bottom_surge", False):
            lines.append(f"   💡 底部放量:")
            lines.append(f"      股票长期下跌后在低位放量，可能是")
            lines.append(f"      主力资金开始吸筹，准备启动行情")
        
        if volume_surge.get("is_breakthrough_surge", False):
            lines.append(f"   💡 突破压力位放量:")
            lines.append(f"      股价突破阻力位时放量，说明多方")
            lines.append(f"      力量强劲，可能继续上涨")
        
        if volume_surge.get("is_early_uptrend_surge", False):
            lines.append(f"   💡 上涨初期持续放量:")
            lines.append(f"      上涨初期成交量持续放大，表明市场")
            lines.append(f"      关注度提升，可能延续上涨趋势")
        
        # 放量详情
        surge_ratio = volume_surge.get("surge_ratio", 0)
        if surge_ratio > 0:
            lines.append(f"   单日放量幅度: {surge_ratio:.2f}%")
        
        continuous_days = volume_surge.get("continuous_days", 0)
        if continuous_days > 0:
            lines.append(f"   连续放量: {continuous_days}天")
    
    # 成交量比率
    volume_analysis = price_trend.get("volume_analysis", {})
    volume_ratio = volume_analysis.get("volume_ratio", 1.0)
    
    lines.append(f"")
    lines.append(f"📊 成交量比率 (5日/20日): {volume_ratio:.2f}")
    if volume_ratio > 1.2:
        lines.append(f"   → 近期成交量明显放大，市场活跃")
    elif volume_ratio < 0.8:
        lines.append(f"   → 近期成交量萎缩，市场观望")
    else:
        lines.append(f"   → 成交量保持稳定")
    
    return "\n".join(lines)


def format_single_ticker_wechat_message(
    ticker: str,
    decision: dict,
    filtered_news_by_ticker: dict,
    fed_expectation: dict | None = None,
    changes_desc: str = "",
    technical_analysis: dict | None = None,
    price_trend_analysis: dict | None = None,
) -> str:
    """
    格式化单个股票的企业微信消息内容
    
    参数:
        ticker: 股票代码
        decision: 该股票的决策信息
        filtered_news_by_ticker: 筛选后的新闻数据（按股票分组）
        fed_expectation: 降息预期数据（可选）
        changes_desc: 变化描述（可选）
        technical_analysis: 该股票的技术分析数据（可选）
        price_trend_analysis: 该股票的价格走势和量价关系分析数据（可选）
    
    返回:
        格式化后的消息字符串
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 获取决策信息
    action = decision.get("action", "hold")
    quantity = decision.get("quantity", 0)
    confidence = decision.get("confidence", 0)
    reasoning = decision.get("reasoning", "")
    score = decision.get("score", {})
    suggested_price = decision.get("suggested_price")
    time_window = decision.get("time_window", "")
    
    # 获取评分详情
    fed_impact = score.get("fed_impact", 0)
    news_impact = score.get("news_impact", 0)
    position_analysis = score.get("position_analysis", 0)
    total_score = score.get("total_score", 0)
    
    # 获取操作图标
    action_emoji = {
        "buy": "📈",
        "sell": "📉",
        "short": "🔻",
        "cover": "🔺",
        "hold": "⏸️"
    }.get(action, "⏸️")
    
    # 格式化操作描述
    action_desc = format_action_description(action, quantity)
    
    # 格式化信心度说明
    confidence_explanation = format_confidence_explanation(confidence)
    
    # 构建消息内容
    message_parts = [
        f"<@delenzhang> 短线新闻分析提醒 - {ticker}",
        f"",
        f"⏰ 时间: {timestamp}",
        f"",
        f"{action_emoji} 操作建议: {action_desc}",
        f"🎯 信心度: {confidence}%",
        f"📊 总分: {total_score}/100",
        f"",
        f"📈 评分详情:",
        f"  • 降息影响: {fed_impact}/50",
        f"  • 新闻影响: {news_impact}/50",
        f"  • 持仓分析: {position_analysis}/50",
    ]
    
    # 添加建议价格和时间窗口（如果有）
    if suggested_price:
        message_parts.append(f"")
        message_parts.append(f"💵 建议价格: ${suggested_price:.2f}")
    
    if time_window:
        message_parts.append(f"⏱️ 时间窗口: {time_window}")
    
    # 添加原因
    if reasoning:
        message_parts.append(f"")
        message_parts.append(f"💭 决策原因:")
        message_parts.append(f"{reasoning}")
    
    # 添加信心度说明
    message_parts.append(f"")
    message_parts.append(confidence_explanation)
    
    # 添加技术分析（如果有）
    if technical_analysis:
        message_parts.append(f"")
        message_parts.append(f"📊 技术分析:")
        technical_str = format_technical_analysis_for_wechat(technical_analysis)
        message_parts.append(technical_str)
    
    # 添加量价关系分析（如果有）
    if price_trend_analysis:
        message_parts.append(f"")
        message_parts.append(f"📈 量价理论分析:")
        volume_price_str = format_volume_price_analysis_for_wechat(price_trend_analysis)
        message_parts.append(volume_price_str)
    
    # 添加相关新闻
    ticker_news = filtered_news_by_ticker.get(ticker, [])
    if ticker_news:
        news_summary = format_news_summary(ticker_news, max_items=None)
        if news_summary:
            message_parts.append(f"")
            message_parts.append(f"📰 相关新闻:")
            message_parts.append(news_summary)
    
    # 添加降息预期信息（如果有）
    if fed_expectation and "error" not in fed_expectation:
        total_cut = fed_expectation.get("total_cut_probability", 0.0) * 100
        no_change = fed_expectation.get("no_change", 0.0) * 100
        message_parts.append(f"")
        message_parts.append(f"📊 降息预期: 降息 {total_cut:.1f}% | 不变 {no_change:.1f}%")
    
    # 添加变化描述（如果有）
    if changes_desc and changes_desc != "操作建议与上次相同":
        message_parts.append(f"")
        message_parts.append(f"🔔 变化详情:")
        message_parts.append(changes_desc)
    
    return "\n".join(message_parts)


def get_default_model_config(project_root: Path) -> tuple[str, str]:
    """
    从 api_models.json 获取第一个模型作为默认配置
    
    参数:
        project_root: 项目根目录路径
    
    返回:
        (模型名称, 模型提供商)
    """
    try:
        from src.llm.models import load_models_from_json
        models_json_path = project_root / "src" / "llm" / "api_models.json"
        models = load_models_from_json(str(models_json_path))
        if models:
            first_model = models[0]
            return first_model.model_name, first_model.provider.value
    except Exception as e:
        print(f"警告: 无法加载 api_models.json，使用默认配置: {e}")
    
    # 回退到默认配置
    return "deepseek-v3", "OPENAI"


def load_operations_history(history_file: Path) -> dict:
    """
    加载历史操作记录
    
    参数:
        history_file: 历史操作记录文件路径
    
    返回:
        历史操作记录字典，格式: {"TICKER": [{"timestamp": "...", "action": "...", ...}, ...], ...}
    """
    if not history_file.exists():
        return {}
    
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载历史操作记录失败: {e}")
        return {}


def save_operations_history(operations: dict, history_file: Path):
    """
    保存操作记录到历史文件
    
    参数:
        operations: 当前操作记录字典，格式: {"TICKER": {"action": "...", "quantity": ..., ...}, ...}
        history_file: 历史操作记录文件路径
    """
    try:
        # 确保目录存在
        history_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载现有历史记录
        history = load_operations_history(history_file)
        
        # 获取当前时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 为每个股票添加当前操作到历史记录
        for ticker, decision in operations.items():
            if ticker not in history:
                history[ticker] = []
            
            # 创建操作记录
            operation_record = {
                "timestamp": timestamp,
                "action": decision.get("action", "hold"),
                "quantity": decision.get("quantity", 0),
                "confidence": decision.get("confidence", 0),
                "reasoning": decision.get("reasoning", ""),
                "suggested_price": decision.get("suggested_price"),
                "time_window": decision.get("time_window", ""),
            }
            
            # 添加到历史记录
            history[ticker].append(operation_record)
        
        # 保存历史记录
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存历史操作记录失败: {e}")


def load_recent_operations_history(days: int = 5, history_file: Path | None = None) -> dict:
    """
    加载近N天的历史操作记录
    
    参数:
        days: 要加载的天数，默认5天
        history_file: 历史操作记录文件路径，如果为None则使用默认路径
    
    返回:
        近N天的历史操作记录字典，格式: {"TICKER": [{"timestamp": "...", "action": "...", ...}, ...], ...}
    """
    # 如果没有指定文件路径，使用默认路径
    if history_file is None:
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        cache_dir = project_root / ".cache" / "short_term_news"
        history_file = cache_dir / "operations_history.json"
    
    # 加载所有历史记录
    all_history = load_operations_history(history_file)
    
    if not all_history:
        return {}
    
    # 计算截止日期
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 过滤出近N天的记录
    recent_history = {}
    for ticker, operations in all_history.items():
        recent_ops = []
        for op in operations:
            try:
                op_timestamp = datetime.strptime(op.get("timestamp", ""), "%Y-%m-%d %H:%M:%S")
                if op_timestamp >= cutoff_date:
                    recent_ops.append(op)
            except (ValueError, TypeError):
                # 如果时间戳格式不正确，跳过这条记录
                continue
        
        if recent_ops:
            recent_history[ticker] = recent_ops
    
    return recent_history


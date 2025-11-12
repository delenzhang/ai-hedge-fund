from colorama import Fore, Style
from tabulate import tabulate
from .analysts import ANALYST_ORDER, ANALYST_CONFIG
import os
import json
import re
from datetime import datetime
from pathlib import Path


def sort_agent_signals(signals):
    """Sort agent signals in a consistent order."""
    # Create order mapping from ANALYST_ORDER
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    analyst_order["Risk Management"] = len(ANALYST_ORDER)  # Add Risk Management at the end

    def extract_text_from_colored_string(colored_str):
        """Extract plain text from a string that may contain ANSI color codes."""
        # Remove ANSI escape sequences (color codes)
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', colored_str)

    return sorted(signals, key=lambda x: analyst_order.get(extract_text_from_colored_string(x[0]), 999))


def print_trading_output(result: dict, model_name: str = None, model_provider: str = None) -> None:
    """
    Print formatted trading results with colored tables for multiple tickers.

    Args:
        result (dict): Dictionary containing decisions and analyst signals for multiple tickers
        model_name: Optional model name used for the analysis
        model_provider: Optional model provider used for the analysis
    """
    decisions = result.get("decisions")
    if not decisions:
        print(f"{Fore.RED}无交易决策可用 / No trading decisions available{Style.RESET_ALL}")
        return

    # Print decisions for each ticker
    for ticker, decision in decisions.items():
        print(f"\n{Fore.WHITE}{Style.BRIGHT}分析报告 / Analysis for {Fore.CYAN}{ticker}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{Style.BRIGHT}{'=' * 50}{Style.RESET_ALL}")

        # Prepare analyst signals table for this ticker
        table_data = []
        for agent, signals in result.get("analyst_signals", {}).items():
            if ticker not in signals:
                continue
                
            # Skip Risk Management agent in the signals section
            if agent == "risk_management_agent":
                continue

            signal = signals[ticker]
            # Get display name from ANALYST_CONFIG if available, otherwise use default formatting
            agent_key = agent.replace("_agent", "")
            if agent_key in ANALYST_CONFIG:
                agent_name = ANALYST_CONFIG[agent_key]["display_name"]
            else:
                agent_name = agent.replace("_agent", "").replace("_", " ").title()
            signal_type = signal.get("signal", "").upper()
            confidence = signal.get("confidence", 0)

            signal_color = {
                "BULLISH": Fore.GREEN,
                "BEARISH": Fore.RED,
                "NEUTRAL": Fore.YELLOW,
            }.get(signal_type, Fore.WHITE)
            
            # Get reasoning if available
            reasoning_str = ""
            if "reasoning" in signal and signal["reasoning"]:
                reasoning = signal["reasoning"]
                
                # Handle different types of reasoning (string, dict, etc.)
                if isinstance(reasoning, str):
                    reasoning_str = reasoning
                elif isinstance(reasoning, dict):
                    # Convert dict to string representation
                    reasoning_str = json.dumps(reasoning, indent=2)
                else:
                    # Convert any other type to string
                    reasoning_str = str(reasoning)
                
                # Wrap long reasoning text to make it more readable
                wrapped_reasoning = ""
                current_line = ""
                # Use a fixed width of 60 characters to match the table column width
                max_line_length = 60
                for word in reasoning_str.split():
                    if len(current_line) + len(word) + 1 > max_line_length:
                        wrapped_reasoning += current_line + "\n"
                        current_line = word
                    else:
                        if current_line:
                            current_line += " " + word
                        else:
                            current_line = word
                if current_line:
                    wrapped_reasoning += current_line
                
                reasoning_str = wrapped_reasoning

            table_data.append(
                [
                    f"{Fore.CYAN}{agent_name}{Style.RESET_ALL}",
                    f"{signal_color}{signal_type}{Style.RESET_ALL}",
                    f"{Fore.WHITE}{confidence}%{Style.RESET_ALL}",
                    f"{Fore.WHITE}{reasoning_str}{Style.RESET_ALL}",
                ]
            )

        # Sort the signals according to the predefined order
        table_data = sort_agent_signals(table_data)

        print(f"\n{Fore.WHITE}{Style.BRIGHT}分析师分析 / AGENT ANALYSIS:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(
            tabulate(
                table_data,
                headers=[f"{Fore.WHITE}分析师 / Agent", "信号 / Signal", "置信度 / Confidence", "推理 / Reasoning"],
                tablefmt="grid",
                colalign=("left", "center", "right", "left"),
            )
        )

        # Print Trading Decision Table
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        # Get reasoning and format it
        reasoning = decision.get("reasoning", "")
        # Wrap long reasoning text to make it more readable
        wrapped_reasoning = ""
        if reasoning:
            current_line = ""
            # Use a fixed width of 60 characters to match the table column width
            max_line_length = 60
            for word in reasoning.split():
                if len(current_line) + len(word) + 1 > max_line_length:
                    wrapped_reasoning += current_line + "\n"
                    current_line = word
                else:
                    if current_line:
                        current_line += " " + word
                    else:
                        current_line = word
            if current_line:
                wrapped_reasoning += current_line

        decision_data = [
            ["操作 / Action", f"{action_color}{action}{Style.RESET_ALL}"],
            ["数量 / Quantity", f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}"],
            [
                "置信度 / Confidence",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
            ],
            ["推理 / Reasoning", f"{Fore.WHITE}{wrapped_reasoning}{Style.RESET_ALL}"],
        ]
        
        print(f"\n{Fore.WHITE}{Style.BRIGHT}交易决策 / TRADING DECISION:{Style.RESET_ALL} [{Fore.CYAN}{ticker}{Style.RESET_ALL}]")
        print(tabulate(decision_data, tablefmt="grid", colalign=("left", "left")))
        
        # 保存报告到文件
        save_report_to_file(ticker, decision, result.get("analyst_signals", {}), result, model_name, model_provider)

    # Print Portfolio Summary
    print(f"\n{Fore.WHITE}{Style.BRIGHT}投资组合摘要 / PORTFOLIO SUMMARY:{Style.RESET_ALL}")
    portfolio_data = []
    
    # Extract portfolio manager reasoning (common for all tickers)
    portfolio_manager_reasoning = None
    for ticker, decision in decisions.items():
        if decision.get("reasoning"):
            portfolio_manager_reasoning = decision.get("reasoning")
            break
            
    analyst_signals = result.get("analyst_signals", {})
    for ticker, decision in decisions.items():
        action = decision.get("action", "").upper()
        action_color = {
            "BUY": Fore.GREEN,
            "SELL": Fore.RED,
            "HOLD": Fore.YELLOW,
            "COVER": Fore.GREEN,
            "SHORT": Fore.RED,
        }.get(action, Fore.WHITE)

        # Calculate analyst signal counts
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0
        if analyst_signals:
            for agent, signals in analyst_signals.items():
                if ticker in signals:
                    signal = signals[ticker].get("signal", "").upper()
                    if signal == "BULLISH":
                        bullish_count += 1
                    elif signal == "BEARISH":
                        bearish_count += 1
                    elif signal == "NEUTRAL":
                        neutral_count += 1

        portfolio_data.append(
            [
                f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
                f"{action_color}{action}{Style.RESET_ALL}",
                f"{action_color}{decision.get('quantity')}{Style.RESET_ALL}",
                f"{Fore.WHITE}{decision.get('confidence'):.1f}%{Style.RESET_ALL}",
                f"{Fore.GREEN}{bullish_count}{Style.RESET_ALL}",
                f"{Fore.RED}{bearish_count}{Style.RESET_ALL}",
                f"{Fore.YELLOW}{neutral_count}{Style.RESET_ALL}",
            ]
        )

    headers = [
        f"{Fore.WHITE}股票代码 / Ticker",
        f"{Fore.WHITE}操作 / Action",
        f"{Fore.WHITE}数量 / Quantity",
        f"{Fore.WHITE}置信度 / Confidence",
        f"{Fore.WHITE}看涨 / Bullish",
        f"{Fore.WHITE}看跌 / Bearish",
        f"{Fore.WHITE}中性 / Neutral",
    ]
    
    # Print the portfolio summary table
    print(
        tabulate(
            portfolio_data,
            headers=headers,
            tablefmt="grid",
            colalign=("left", "center", "right", "right", "center", "center", "center"),
        )
    )
    
    # Print Portfolio Manager's reasoning if available
    if portfolio_manager_reasoning:
        # Handle different types of reasoning (string, dict, etc.)
        reasoning_str = ""
        if isinstance(portfolio_manager_reasoning, str):
            reasoning_str = portfolio_manager_reasoning
        elif isinstance(portfolio_manager_reasoning, dict):
            # Convert dict to string representation
            reasoning_str = json.dumps(portfolio_manager_reasoning, indent=2)
        else:
            # Convert any other type to string
            reasoning_str = str(portfolio_manager_reasoning)
            
        # Wrap long reasoning text to make it more readable
        wrapped_reasoning = ""
        current_line = ""
        # Use a fixed width of 60 characters to match the table column width
        max_line_length = 60
        for word in reasoning_str.split():
            if len(current_line) + len(word) + 1 > max_line_length:
                wrapped_reasoning += current_line + "\n"
                current_line = word
            else:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
        if current_line:
            wrapped_reasoning += current_line
            
        print(f"\n{Fore.WHITE}{Style.BRIGHT}投资组合策略 / Portfolio Strategy:{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{wrapped_reasoning}{Style.RESET_ALL}")
    
    # Print confidence recommendations for each decision
    print(f"\n{Fore.WHITE}{Style.BRIGHT}置信度应用建议 / CONFIDENCE RECOMMENDATIONS:{Style.RESET_ALL}")
    print(f"{Fore.WHITE}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}")
    
    # Group decisions by action type for summary
    long_positions = []  # BUY, COVER
    short_positions = []  # SHORT, SELL
    
    for ticker, decision in decisions.items():
        confidence = decision.get('confidence', 0)
        action = decision.get('action', '').upper()
        
        # Skip hold actions
        if action == 'HOLD':
            continue
        
        # Categorize by action type
        if action in ['BUY', 'COVER']:
            long_positions.append((ticker, confidence, action))
        elif action in ['SHORT', 'SELL']:
            short_positions.append((ticker, confidence, action))
            
        recommendation = get_confidence_recommendation(confidence, action)
        recommendation_color = recommendation['color']
        
        # Display action type with color
        action_display = {
            'BUY': f'{Fore.GREEN}做多/买入{Style.RESET_ALL}',
            'SELL': f'{Fore.RED}卖出{Style.RESET_ALL}',
            'SHORT': f'{Fore.RED}做空{Style.RESET_ALL}',
            'COVER': f'{Fore.GREEN}平空/回补{Style.RESET_ALL}',
        }.get(action, action)
        
        print(f"\n{Fore.CYAN}{ticker}{Style.RESET_ALL} - {action_display} - {Fore.WHITE}置信度: {confidence:.1f}%{Style.RESET_ALL}")
        print(f"  {recommendation_color}{recommendation['message']}{Style.RESET_ALL}")
        if recommendation.get('details'):
            for detail in recommendation['details']:
                print(f"    • {Fore.WHITE}{detail}{Style.RESET_ALL}")
    
    # Print summary by action type
    if long_positions or short_positions:
        print(f"\n{Fore.WHITE}{Style.BRIGHT}{'=' * 70}{Style.RESET_ALL}")
        print(f"\n{Fore.WHITE}{Style.BRIGHT}操作类型总结 / ACTION TYPE SUMMARY:{Style.RESET_ALL}")
        
        if long_positions:
            avg_long_confidence = sum(conf for _, conf, _ in long_positions) / len(long_positions)
            print(f"\n{Fore.GREEN}做多/买入操作 (BUY/COVER):{Style.RESET_ALL}")
            print(f"  数量: {len(long_positions)} 个")
            print(f"  平均置信度: {Fore.WHITE}{avg_long_confidence:.1f}%{Style.RESET_ALL}")
            long_recommendation = get_confidence_recommendation(avg_long_confidence, 'BUY')
            print(f"  总体建议: {long_recommendation['color']}{long_recommendation['summary']}{Style.RESET_ALL}")
        
        if short_positions:
            avg_short_confidence = sum(conf for _, conf, _ in short_positions) / len(short_positions)
            print(f"\n{Fore.RED}做空/卖出操作 (SHORT/SELL):{Style.RESET_ALL}")
            print(f"  数量: {len(short_positions)} 个")
            print(f"  平均置信度: {Fore.WHITE}{avg_short_confidence:.1f}%{Style.RESET_ALL}")
            short_recommendation = get_confidence_recommendation(avg_short_confidence, 'SHORT')
            print(f"  总体建议: {short_recommendation['color']}{short_recommendation['summary']}{Style.RESET_ALL}")


def remove_ansi_codes(text: str) -> str:
    """Remove ANSI color codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def generate_markdown_report(ticker: str, decision: dict, analyst_signals: dict, result: dict, model_name: str = None, model_provider: str = None) -> str:
    """
    生成单个股票的 Markdown 格式分析报告
    
    Args:
        ticker: 股票代码
        decision: 交易决策
        analyst_signals: 分析师信号
        result: 完整的结果字典
        model_name: 使用的模型名称
        model_provider: 使用的模型提供商
        
    Returns:
        Markdown 格式的报告字符串
    """
    markdown = []
    
    # 标题
    markdown.append(f"# 分析报告 / Analysis for {ticker}\n")
    markdown.append(f"{'=' * 50}\n")
    
    # 添加模型信息
    if model_name:
        model_info = f"**模型 / Model:** {model_name}"
        if model_provider:
            model_info += f" ({model_provider})"
        markdown.append(f"{model_info}\n\n")
    
    # 分析师分析表格
    markdown.append(f"\n## 分析师分析 / AGENT ANALYSIS: [{ticker}]\n")
    
    # 准备分析师信号数据
    table_data = []
    for agent, signals in analyst_signals.items():
        if ticker not in signals:
            continue
            
        # 跳过风险管理代理
        if agent == "risk_management_agent":
            continue

        signal = signals[ticker]
        # 获取显示名称
        agent_key = agent.replace("_agent", "")
        if agent_key in ANALYST_CONFIG:
            agent_name = ANALYST_CONFIG[agent_key]["display_name"]
        else:
            agent_name = agent.replace("_agent", "").replace("_", " ").title()
        
        signal_type = signal.get("signal", "").upper()
        confidence = signal.get("confidence", 0)
        
        # 获取推理
        reasoning_str = ""
        if "reasoning" in signal and signal["reasoning"]:
            reasoning = signal["reasoning"]
            if isinstance(reasoning, str):
                reasoning_str = reasoning
            elif isinstance(reasoning, dict):
                reasoning_str = json.dumps(reasoning, indent=2, ensure_ascii=False)
            else:
                reasoning_str = str(reasoning)
        
        table_data.append({
            "agent": agent_name,
            "signal": signal_type,
            "confidence": f"{confidence}%",
            "reasoning": reasoning_str
        })
    
    # 按顺序排序
    analyst_order = {display: idx for idx, (display, _) in enumerate(ANALYST_ORDER)}
    table_data.sort(key=lambda x: analyst_order.get(x["agent"], 999))
    
    # 生成 Markdown 表格
    markdown.append("| 分析师 / Agent | 信号 / Signal | 置信度 / Confidence | 推理 / Reasoning |\n")
    markdown.append("|----------------|---------------|---------------------|-------------------|\n")
    
    for row in table_data:
        # 转义 Markdown 特殊字符
        agent = row["agent"].replace("|", "\\|")
        signal = row["signal"].replace("|", "\\|")
        confidence = row["confidence"].replace("|", "\\|")
        reasoning = row["reasoning"].replace("|", "\\|").replace("\n", "<br>")
        markdown.append(f"| {agent} | {signal} | {confidence} | {reasoning} |\n")
    
    # 交易决策
    markdown.append(f"\n## 交易决策 / TRADING DECISION: [{ticker}]\n")
    
    action = decision.get("action", "").upper()
    quantity = decision.get("quantity", 0)
    confidence = decision.get("confidence", 0)
    reasoning = decision.get("reasoning", "")
    
    markdown.append("| 项目 | 内容 |\n")
    markdown.append("|------|------|\n")
    markdown.append(f"| 操作 / Action | {action} |\n")
    markdown.append(f"| 数量 / Quantity | {quantity} |\n")
    markdown.append(f"| 置信度 / Confidence | {confidence:.1f}% |\n")
    markdown.append(f"| 推理 / Reasoning | {reasoning.replace('|', '\\|').replace('\n', '<br>')} |\n")
    
    # 投资组合摘要（仅当前股票）
    markdown.append(f"\n## 投资组合摘要 / PORTFOLIO SUMMARY\n")
    
    # 计算信号统计
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    for agent, signals in analyst_signals.items():
        if ticker in signals:
            signal = signals[ticker].get("signal", "").upper()
            if signal == "BULLISH":
                bullish_count += 1
            elif signal == "BEARISH":
                bearish_count += 1
            elif signal == "NEUTRAL":
                neutral_count += 1
    
    markdown.append("| 股票代码 / Ticker | 操作 / Action | 数量 / Quantity | 置信度 / Confidence | 看涨 / Bullish | 看跌 / Bearish | 中性 / Neutral |\n")
    markdown.append("|-------------------|---------------|-----------------|---------------------|----------------|----------------|----------------|\n")
    markdown.append(f"| {ticker} | {action} | {quantity} | {confidence:.1f}% | {bullish_count} | {bearish_count} | {neutral_count} |\n")
    
    # 投资组合策略
    portfolio_manager_reasoning = reasoning
    if portfolio_manager_reasoning:
        markdown.append(f"\n### 投资组合策略 / Portfolio Strategy\n\n")
        markdown.append(f"{portfolio_manager_reasoning.replace('|', '\\|')}\n")
    
    # 置信度建议
    markdown.append(f"\n## 置信度应用建议 / CONFIDENCE RECOMMENDATIONS\n")
    markdown.append(f"{'=' * 70}\n\n")
    
    if action != 'HOLD':
        recommendation = get_confidence_recommendation(confidence, action)
        action_display = {
            'BUY': '做多/买入',
            'SELL': '卖出',
            'SHORT': '做空',
            'COVER': '平空/回补',
        }.get(action, action)
        
        markdown.append(f"**{ticker}** - {action_display} - 置信度: {confidence:.1f}%\n\n")
        markdown.append(f"{recommendation['message']}\n\n")
        
        if recommendation.get('details'):
            markdown.append("详细建议：\n")
            for detail in recommendation['details']:
                markdown.append(f"- {detail}\n")
    
    return "".join(markdown)


def save_report_to_file(ticker: str, decision: dict, analyst_signals: dict, result: dict, model_name: str = None, model_provider: str = None) -> None:
    """
    将分析报告保存到 report 文件夹
    
    Args:
        ticker: 股票代码
        decision: 交易决策
        analyst_signals: 分析师信号
        result: 完整的结果字典
        model_name: 使用的模型名称
        model_provider: 使用的模型提供商
    """
    # 获取当前日期
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 构建报告目录路径（相对于项目根目录）
    project_root = Path(__file__).parent.parent.parent
    report_dir = project_root / "report"
    
    # 确保目录存在
    report_dir.mkdir(exist_ok=True)
    
    # 生成文件名：股票名-模型名-日期.md（如果提供了模型名）
    if model_name:
        # 清理模型名称，移除可能不适合文件名的字符
        # 保留字母、数字、连字符和下划线，其他字符替换为连字符
        safe_model_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in model_name)
        # 移除连续的连字符
        while "--" in safe_model_name:
            safe_model_name = safe_model_name.replace("--", "-")
        # 移除开头和结尾的连字符
        safe_model_name = safe_model_name.strip("-")
        filename = f"{ticker}-{safe_model_name}-{current_date}.md"
    else:
        filename = f"{ticker}-{current_date}.md"
    filepath = report_dir / filename
    
    # 生成 Markdown 报告
    markdown_content = generate_markdown_report(ticker, decision, analyst_signals, result, model_name, model_provider)
    
    # 写入文件（如果同一天的分析，直接替换）
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        print(f"{Fore.GREEN}报告已保存到: {filepath}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}保存报告失败: {e}{Style.RESET_ALL}")


def get_confidence_recommendation(confidence: float, action: str = 'BUY') -> dict:
    """
    根据置信度和操作类型返回应用建议
    
    Args:
        confidence: 置信度分数 (0-100)
        action: 操作类型 ('BUY', 'SELL', 'SHORT', 'COVER')
        
    Returns:
        包含建议信息的字典
    """
    action_upper = action.upper()
    is_long = action_upper in ['BUY', 'COVER']  # 做多操作
    is_short = action_upper in ['SHORT', 'SELL']  # 做空操作
    
    if confidence >= 90:
        if is_long:
            return {
                'color': Fore.GREEN,
                'level': '高置信度',
                'message': '✅ 高置信度 (90-100%)：强烈建议做多，可考虑较大仓位',
                'summary': '强烈建议做多，适合较大仓位配置',
                'details': [
                    '能力圈内卓越业务，价格有吸引力',
                    '适合较大仓位做多配置',
                    '建议密切监控，但可长期持有',
                    '可考虑分批建仓，降低入场风险'
                ]
            }
        else:  # is_short
            return {
                'color': Fore.GREEN,
                'level': '高置信度',
                'message': '✅ 高置信度 (90-100%)：强烈建议做空，可考虑较大仓位',
                'summary': '强烈建议做空，适合较大仓位配置',
                'details': [
                    '业务基本面严重恶化或严重高估',
                    '适合较大仓位做空配置',
                    '建议设置止损点，防止反弹风险',
                    '密切关注市场情绪和基本面变化'
                ]
            }
    elif confidence >= 70:
        if is_long:
            return {
                'color': Fore.GREEN,
                'level': '较高置信度',
                'message': '✅ 较高置信度 (70-89%)：建议做多，适合中等仓位',
                'summary': '建议做多，适合中等仓位配置',
                'details': [
                    '好业务，有护城河，估值合理',
                    '适合中等仓位做多配置',
                    '建议定期审查持仓',
                    '可设置止盈目标，锁定利润'
                ]
            }
        else:  # is_short
            return {
                'color': Fore.GREEN,
                'level': '较高置信度',
                'message': '✅ 较高置信度 (70-89%)：建议做空，适合中等仓位',
                'summary': '建议做空，适合中等仓位配置',
                'details': [
                    '基本面转弱或估值偏高',
                    '适合中等仓位做空配置',
                    '建议设置严格止损，控制风险',
                    '密切关注反弹信号，及时平仓'
                ]
            }
    elif confidence >= 50:
        if is_long:
            return {
                'color': Fore.YELLOW,
                'level': '中等置信度',
                'message': '⚠️  中等置信度 (50-69%)：谨慎做多，建议小仓位试探',
                'summary': '谨慎做多，建议小仓位试探',
                'details': [
                    '信号混杂，需要更多信息或更好价格',
                    '建议小仓位试探性做多建仓',
                    '等待更多确认信号或更好入场价格',
                    '设置严格止损点，控制下行风险'
                ]
            }
        else:  # is_short
            return {
                'color': Fore.YELLOW,
                'level': '中等置信度',
                'message': '⚠️  中等置信度 (50-69%)：谨慎做空，建议小仓位试探',
                'summary': '谨慎做空，建议小仓位试探',
                'details': [
                    '做空信号不够强烈，存在反弹风险',
                    '建议小仓位试探性做空',
                    '等待更明确的下跌信号',
                    '设置严格止损点，防止逼空风险'
                ]
            }
    elif confidence >= 30:
        if is_long:
            return {
                'color': Fore.RED,
                'level': '低置信度',
                'message': '❌ 低置信度 (30-49%)：不建议做多',
                'summary': '不建议做多，建议避免或极小仓位',
                'details': [
                    '超出能力圈或基本面令人担忧',
                    '建议避免做多或极小仓位',
                    '等待更明确的看涨信号',
                    '如果必须建仓，严格设置止损'
                ]
            }
        else:  # is_short
            return {
                'color': Fore.RED,
                'level': '低置信度',
                'message': '❌ 低置信度 (30-49%)：不建议做空',
                'summary': '不建议做空，做空风险较高',
                'details': [
                    '做空信号不够明确，存在反弹风险',
                    '建议避免做空或极小仓位',
                    '等待更明确的看跌信号',
                    '做空风险较大，建议观望'
                ]
            }
    else:
        if is_long:
            return {
                'color': Fore.RED,
                'level': '极低置信度',
                'message': '❌ 极低置信度 (0-29%)：强烈不建议做多',
                'summary': '强烈不建议做多，建议避免执行',
                'details': [
                    '业务差或严重高估',
                    '建议避免执行做多交易',
                    '等待更好的投资机会',
                    '如果已持仓，考虑减仓或止损'
                ]
            }
        else:  # is_short
            return {
                'color': Fore.RED,
                'level': '极低置信度',
                'message': '❌ 极低置信度 (0-29%)：强烈不建议做空',
                'summary': '强烈不建议做空，做空风险极高',
                'details': [
                    '做空信号极弱，存在强烈反弹风险',
                    '建议避免执行做空交易',
                    '等待更明确的看跌信号',
                    '做空风险极高，建议观望或考虑做多'
                ]
            }


def print_backtest_results(table_rows: list) -> None:
    """Print the backtest results in a nicely formatted table"""
    # Clear the screen
    os.system("cls" if os.name == "nt" else "clear")

    # Split rows into ticker rows and summary rows
    ticker_rows = []
    summary_rows = []

    for row in table_rows:
        if isinstance(row[1], str) and "PORTFOLIO SUMMARY" in row[1]:
            summary_rows.append(row)
        else:
            ticker_rows.append(row)

    # Display latest portfolio summary
    if summary_rows:
        # Pick the most recent summary by date (YYYY-MM-DD)
        latest_summary = max(summary_rows, key=lambda r: r[0])
        print(f"\n{Fore.WHITE}{Style.BRIGHT}投资组合摘要 / PORTFOLIO SUMMARY:{Style.RESET_ALL}")

        # Adjusted indexes after adding Long/Short Shares
        position_str = latest_summary[7].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        cash_str     = latest_summary[8].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")
        total_str    = latest_summary[9].split("$")[1].split(Style.RESET_ALL)[0].replace(",", "")

        print(f"现金余额 / Cash Balance: {Fore.CYAN}${float(cash_str):,.2f}{Style.RESET_ALL}")
        print(f"持仓总价值 / Total Position Value: {Fore.YELLOW}${float(position_str):,.2f}{Style.RESET_ALL}")
        print(f"总价值 / Total Value: {Fore.WHITE}${float(total_str):,.2f}{Style.RESET_ALL}")
        print(f"投资组合回报 / Portfolio Return: {latest_summary[10]}")
        if len(latest_summary) > 14 and latest_summary[14]:
            print(f"基准回报 / Benchmark Return: {latest_summary[14]}")

        # Display performance metrics if available
        if latest_summary[11]:  # Sharpe ratio
            print(f"夏普比率 / Sharpe Ratio: {latest_summary[11]}")
        if latest_summary[12]:  # Sortino ratio
            print(f"索提诺比率 / Sortino Ratio: {latest_summary[12]}")
        if latest_summary[13]:  # Max drawdown
            print(f"最大回撤 / Max Drawdown: {latest_summary[13]}")

    # Add vertical spacing
    print("\n" * 2)

    # Print the table with just ticker rows
    print(
        tabulate(
            ticker_rows,
            headers=[
                "日期 / Date",
                "股票代码 / Ticker",
                "操作 / Action",
                "数量 / Quantity",
                "价格 / Price",
                "多头持仓 / Long Shares",
                "空头持仓 / Short Shares",
                "持仓价值 / Position Value",
            ],
            tablefmt="grid",
            colalign=(
                "left",    # Date
                "left",    # Ticker
                "center",  # Action
                "right",   # Quantity
                "right",   # Price
                "right",   # Long Shares
                "right",   # Short Shares
                "right",   # Position Value
            ),
        )
    )

    # Add vertical spacing
    print("\n" * 4)


def format_backtest_row(
    date: str,
    ticker: str,
    action: str,
    quantity: float,
    price: float,
    long_shares: float = 0,
    short_shares: float = 0,
    position_value: float = 0,
    is_summary: bool = False,
    total_value: float = None,
    return_pct: float = None,
    cash_balance: float = None,
    total_position_value: float = None,
    sharpe_ratio: float = None,
    sortino_ratio: float = None,
    max_drawdown: float = None,
    benchmark_return_pct: float | None = None,
) -> list[any]:
    """Format a row for the backtest results table"""
    # Color the action
    action_color = {
        "BUY": Fore.GREEN,
        "COVER": Fore.GREEN,
        "SELL": Fore.RED,
        "SHORT": Fore.RED,
        "HOLD": Fore.WHITE,
    }.get(action.upper(), Fore.WHITE)

    if is_summary:
        return_color = Fore.GREEN if return_pct >= 0 else Fore.RED
        benchmark_str = ""
        if benchmark_return_pct is not None:
            bench_color = Fore.GREEN if benchmark_return_pct >= 0 else Fore.RED
            benchmark_str = f"{bench_color}{benchmark_return_pct:+.2f}%{Style.RESET_ALL}"
        return [
            date,
            f"{Fore.WHITE}{Style.BRIGHT}PORTFOLIO SUMMARY{Style.RESET_ALL}",
            "",  # Action
            "",  # Quantity
            "",  # Price
            "",  # Long Shares
            "",  # Short Shares
            f"{Fore.YELLOW}${total_position_value:,.2f}{Style.RESET_ALL}",  # Total Position Value
            f"{Fore.CYAN}${cash_balance:,.2f}{Style.RESET_ALL}",  # Cash Balance
            f"{Fore.WHITE}${total_value:,.2f}{Style.RESET_ALL}",  # Total Value
            f"{return_color}{return_pct:+.2f}%{Style.RESET_ALL}",  # Return
            f"{Fore.YELLOW}{sharpe_ratio:.2f}{Style.RESET_ALL}" if sharpe_ratio is not None else "",  # Sharpe Ratio
            f"{Fore.YELLOW}{sortino_ratio:.2f}{Style.RESET_ALL}" if sortino_ratio is not None else "",  # Sortino Ratio
            f"{Fore.RED}{max_drawdown:.2f}%{Style.RESET_ALL}" if max_drawdown is not None else "",  # Max Drawdown (signed)
            benchmark_str,  # Benchmark (S&P 500)
        ]
    else:
        return [
            date,
            f"{Fore.CYAN}{ticker}{Style.RESET_ALL}",
            f"{action_color}{action.upper()}{Style.RESET_ALL}",
            f"{action_color}{quantity:,.0f}{Style.RESET_ALL}",
            f"{Fore.WHITE}{price:,.2f}{Style.RESET_ALL}",
            f"{Fore.GREEN}{long_shares:,.0f}{Style.RESET_ALL}",   # Long Shares
            f"{Fore.RED}{short_shares:,.0f}{Style.RESET_ALL}",    # Short Shares
            f"{Fore.YELLOW}{position_value:,.2f}{Style.RESET_ALL}",
        ]

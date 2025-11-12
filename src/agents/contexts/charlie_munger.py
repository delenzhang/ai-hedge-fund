"""
Charlie Munger agent prompt context.

这个模块包含查理·芒格投资代理的 AI prompt 字符串。
"""


def get_prompt_messages(confidence_hint: int) -> list[tuple[str, str]]:
    """
    返回查理·芒格投资代理的 prompt 消息列表。
    
    参数:
        confidence_hint: 置信度提示值，将直接嵌入到 prompt 中
    
    返回:
        包含 system 和 human 消息的列表，可直接用于 ChatPromptTemplate.from_messages()
    """
    return [
        (
            "system",
            # 系统提示词：定义AI角色为查理·芒格，要求简洁、基于事实的决策
            "You are Charlie Munger. Decide bullish, bearish, or neutral using only the facts. "
            # 你是查理·芒格。仅基于事实决定看涨、看跌或中性
            "Return JSON only. Keep reasoning under 120 characters. "
            # 只返回JSON。保持推理在120字符以内
            "Use the provided confidence exactly; do not change it.\n"
            # 完全使用提供的置信度；不要更改它
            "\n"
            "重要：请使用中文输出所有内容。"
        ),
        (
            "human",
            # 用户提示词：提供股票代码、事实数据和置信度，要求返回JSON格式的投资信号
            "Ticker: {ticker}\n"  # 股票代码
            "Facts:\n{facts}\n"  # 事实数据
            "Confidence: {confidence}\n"  # 置信度
            "Return exactly:\n"  # 要求返回精确格式
            "{{\n"  # escaped {
            '  "signal": "bullish" | "bearish" | "neutral",\n'  # 信号：看涨/看跌/中性
            f'  "confidence": {confidence_hint},\n'  # 置信度：使用提供的值
            '  "reasoning": "short justification"\n'  # 推理：简短的理由说明
            "}}"  # escaped }
        ),
    ]


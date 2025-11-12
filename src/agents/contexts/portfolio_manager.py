"""
Portfolio Manager agent prompt context.

这个模块包含投资组合经理代理的 AI prompt 字符串。
"""


def get_prompt_messages() -> list[tuple[str, str]]:
    """
    返回投资组合经理代理的 prompt 消息列表。
    
    返回:
        包含 system 和 human 消息的列表，可直接用于 ChatPromptTemplate.from_messages()
    """
    return [
        (
            "system",
            # 系统提示词：定义AI角色为投资组合经理，说明决策规则
            "You are a portfolio manager.\n"
            # 你是一名投资组合经理
            "Inputs per ticker: analyst signals and allowed actions with max qty (already validated).\n"
            # 每个股票代码的输入：分析师信号和允许的操作（含最大数量，已验证）
            "Pick one allowed action per ticker and a quantity ≤ the max. "
            # 为每个股票代码选择一个允许的操作，数量≤最大值
            "Keep reasoning very concise (max 100 chars). No cash or margin math. Return JSON only.\n"
            # 保持推理非常简洁（最多100字符）。不需要现金或保证金计算。只返回JSON
            "\n"
            "重要：请使用中文输出所有内容。"
        ),
        (
            "human",
            # 用户提示词：提供分析师信号和允许的操作，要求返回JSON格式的交易决策
            "Signals:\n{signals}\n\n"  # 信号：分析师的投资信号
            "Allowed:\n{allowed}\n\n"  # 允许的操作：每个股票代码允许的交易操作和最大数量
            "Format:\n"  # 格式要求
            "{{\n"
            '  "decisions": {{\n'  # 决策字典
            '    "TICKER": {{"action":"...","quantity":int,"confidence":int,"reasoning":"..."}}\n'  # 每个股票代码的决策：操作、数量、置信度、推理
            "  }}\n"
            "}}"
        ),
    ]


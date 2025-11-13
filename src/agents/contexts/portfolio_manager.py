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
            "For buy/sell actions, provide a suggested_price (target entry/exit price per share). "
            # 对于买入/卖出操作，提供建议价格（目标入场/出场价格）
            "The suggested_price should be based on the current market price and your analysis. "
            # 建议价格应基于当前市场价格和你的分析
            "For buy actions, suggest a price at or below current price if you expect a good entry. "
            # 对于买入操作，如果你预期一个好的入场点，建议价格应在当前价格或以下
            "For sell actions, suggest a price at or above current price if you expect a good exit. "
            # 对于卖出操作，如果你预期一个好的出场点，建议价格应在当前价格或以上
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
            "Current Prices:\n{prices}\n\n"  # 当前价格：每个股票代码的当前市场价格
            "Format:\n"  # 格式要求
            "{{\n"
            '  "decisions": {{\n'  # 决策字典
            '    "TICKER": {{"action":"...","quantity":int,"confidence":int,"reasoning":"...","suggested_price":float|null}}\n'  # 每个股票代码的决策：操作、数量、置信度、推理、建议价格（可选）
            "  }}\n"
            "}}\n"
            "Note: suggested_price is optional. Provide it for buy/sell/short/cover actions when you have a target price. Use null for hold or when no specific price is recommended."  # 注意：建议价格是可选的。对于买入/卖出/做空/平仓操作，如果有目标价格则提供。对于持有或没有特定价格建议时使用null
        ),
    ]


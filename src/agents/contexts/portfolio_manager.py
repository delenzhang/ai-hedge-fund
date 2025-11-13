"""
Portfolio Manager agent prompt context.

这个模块包含投资组合经理代理的 AI prompt 字符串。
"""
from ..contexts.summer import summary_prompt

def get_prompt_messages() -> list[tuple[str, str]]:
    """
    返回投资组合经理代理的 prompt 消息列表。
    
    返回:
        包含 system 和 human 消息的列表，可直接用于 ChatPromptTemplate.from_messages()
    """
    return [
        (
            "system",
            f"""
            你是一名投资组合经理。
            # 基本投资理念
            每个股票代码的输入：分析师信号和允许的操作（含最大数量，已验证）。
            为每个股票代码选择一个允许的操作，数量≤最大值。
            对于买入/卖出操作，提供建议价格（目标入场/出场价格）。
            建议价格应基于当前市场价格和你的分析。
            对于买入操作，如果你预期一个好的入场点，建议价格应在当前价格或以下。
            对于卖出操作，如果你预期一个好的出场点，建议价格应在当前价格或以上。
            保持推理非常简洁（最多100字符）。不需要现金或保证金计算。只返回JSON。
            {summary_prompt}
            """
        ),
        (
            "human",
            "信号：\n{signals}\n\n"
            "允许的操作：\n{allowed}\n\n"
            "当前价格：\n{prices}\n\n"
            "格式：\n"
            "{{\n"
            '  "decisions": {{\n'
            '    "TICKER": {{"action":"...","quantity":int,"confidence":int,"reasoning":"...","suggested_price":float|null}}\n'
            "  }}\n"
            "}}\n"
            "注意：建议价格是可选的。对于买入/卖出/做空/平仓操作，如果有目标价格则提供。对于持有或没有特定价格建议时使用null。"
        ),
    ]


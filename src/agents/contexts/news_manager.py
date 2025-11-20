"""
News Manager agent prompt context.

这个模块包含新闻管理代理的 AI prompt 字符串。
"""


def get_news_filter_prompt_messages() -> list[tuple[str, str]]:
    """
    返回新闻筛选的 prompt 消息列表（优化版本）。
    
    优化说明：
    - 减少重复的筛选标准说明
    - 简化 prompt 内容，降低 token 消耗
    
    返回:
        包含 system 和 human 消息的列表，用于筛选与股票相关的新闻
    """
    return [
        (
            "system",
            """你是一名金融新闻分析师，负责筛选与特定股票相关的新闻。

筛选标准（按优先级）：
1. 直接相关：标题/标签明确提及股票代码或公司名称
2. 业务相关：涉及该公司主要业务领域、行业动态
3. 宏观影响：可能影响该股票的国家政策、经济数据、地缘政治
4. 市场情绪：可能影响整体市场情绪，进而影响该股票

只选择真正可能影响股票价格的新闻，避免无关新闻。"""
        ),
        (
            "human",
            "股票代码：{ticker}\n\n"
            "待筛选新闻（共 {news_count} 条）：\n{all_news}\n\n"
            "请从以上新闻中筛选出与股票 {ticker} 相关的新闻。\n\n"
            "返回格式：JSON 对象，包含 'news' 字段，值为新闻数组。\n"
            "每个新闻对象需保持原始结构（datetime, title, raw_time, labels, news_id, url 等），"
            "并添加：\n"
            "1. 'title_cn': 标题中文翻译（英文标题必须翻译）\n"
            "2. 'relevance_reason': 入选理由（仅中文，简洁说明）\n\n"
            "relevance_reason 示例：\n"
            "- \"直接提及股票代码\"\n"
            "- \"业务相关：支付行业动态\"\n"
            "- \"宏观影响：中国政策变化\"\n"
            "- \"市场情绪：科技股走势\"\n\n"
            "如无相关新闻，返回 {{'news': []}}。"
        ),
    ]


"""
新闻统一管理模块

提供新闻相关的工具函数，包括：
- 获取新闻唯一标识键（用于去重）
- 从多个新闻源实时获取最新新闻（不存储缓存）
"""
from typing import List

from src.news.financialjuice import fetch_latest_news as fetch_financialjuice_news
from src.news.trump import fetch_trump_news


def get_news_key(item: dict) -> str:
    """
    获取新闻的唯一标识键，用于去重
    
    优先级：
    1. news_id (financialjuice 使用)
    2. status_id (trump 使用)
    3. title + datetime (作为后备)
    
    参数:
        item: 新闻项字典
    
    返回:
        唯一标识字符串
    """
    # 优先使用 news_id
    news_id = item.get("news_id", 0)
    if news_id and news_id != 0:
        return f"id_{news_id}"
    
    # 其次使用 status_id (trump 使用)
    status_id = item.get("status_id", "")
    if status_id:
        return f"status_{status_id}"
    
    # 最后使用 title + datetime
    title = item.get("title", "")
    datetime_str = item.get("datetime", "")
    return f"title_{title}_{datetime_str}"


def fetch_latest_news() -> List[dict]:
    """
    从所有新闻源实时获取最新新闻（不存储缓存）
    
    返回:
        新闻列表，按时间倒序排序，已去重
    """
    all_new_news = []
    
    # 1. 从 financialjuice 获取新闻
    print("正在从 FinancialJuice 获取新闻...")
    try:
        financialjuice_news = fetch_financialjuice_news(use_cache=False)
        # 添加来源标识
        for item in financialjuice_news:
            if "source" not in item:
                item["source"] = "financialjuice"
        all_new_news.extend(financialjuice_news)
        print(f"从 FinancialJuice 获取到 {len(financialjuice_news)} 条新闻")
    except Exception as e:
        print(f"警告: 从 FinancialJuice 获取新闻失败: {e}")
    
    # 2. 从 trump 获取新闻
    print("正在从 Trump 获取新闻...")
    try:
        trump_news = fetch_trump_news(limit=50)
        all_new_news.extend(trump_news)
        print(f"从 Trump 获取到 {len(trump_news)} 条新闻")
    except Exception as e:
        print(f"警告: 从 Trump 获取新闻失败: {e}")
    
    # 去重
        news_dict = {}
        for item in all_new_news:
            key = get_news_key(item)
            news_dict[key] = item
    
    # 转换回列表并按日期倒序排序
        merged_news = list(news_dict.values())
        merged_news = sorted(merged_news, key=lambda x: x.get("datetime", ""), reverse=True)
    
    print(f"总共获取到 {len(merged_news)} 条新闻（已去重）")
    return merged_news


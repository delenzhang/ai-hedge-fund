"""
新闻统一管理模块

整合多个新闻源（financialjuice、trump等），统一存储到 .cache/news_manager/news_manager.json
按时间倒序排序，并去重。
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List

from src.news.financialjuice import fetch_latest_news as fetch_financialjuice_news
from src.news.trump import fetch_trump_news

# 缓存文件路径
CACHE_DIR = Path(".cache/news_manager")
CACHE_FILE = CACHE_DIR / "news_manager.json"


def load_cached_news() -> List[dict]:
    """
    从缓存文件加载新闻数据
    返回新闻列表，如果文件不存在则返回空列表
    """
    if not CACHE_FILE.exists():
        return []
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        print(f"警告: 无法读取缓存文件: {e}")
        return []


def save_cached_news(news_list: List[dict]):
    """
    保存新闻数据到缓存文件
    """
    try:
        # 确保目录存在
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # 保存到文件
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告: 无法保存缓存文件: {e}")


def get_news_key(item: dict) -> str:
    """
    获取新闻的唯一标识键，用于去重
    
    优先级：
    1. news_id (financialjuice 使用)
    2. status_id (trump 使用)
    3. title + datetime (作为后备)
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


def merge_and_deduplicate_news(new_news: List[dict], cached_news: List[dict]) -> List[dict]:
    """
    合并新新闻和缓存新闻，并去重
    
    参数:
        new_news: 新获取的新闻列表
        cached_news: 缓存中的新闻列表
    
    返回:
        去重后的新闻列表，按时间倒序排序
    """
    # 创建以唯一标识为键的字典
    news_dict = {}
    
    # 首先添加缓存中的新闻
    for item in cached_news:
        key = get_news_key(item)
        news_dict[key] = item
    
    # 然后添加新新闻（会覆盖相同标识的旧新闻）
    for item in new_news:
        key = get_news_key(item)
        news_dict[key] = item
    
    # 转换回列表并按日期倒序排序
    merged_list = list(news_dict.values())
    merged_list = sorted(merged_list, key=lambda x: x.get("datetime", ""), reverse=True)
    
    return merged_list


def fetch_latest_news(use_cache: bool = True) -> List[dict]:
    """
    从所有新闻源获取最新新闻，统一存储到 .cache/news_manager/news_manager.json
    
    参数:
        use_cache: 是否使用缓存，默认为 True。如果为 True，会与缓存文件对比并合并数据。
    
    返回:
        新闻列表，按时间倒序排序，已去重
    """
    # 加载缓存数据
    cached_news = []
    if use_cache:
        cached_news = load_cached_news()
    
    # 从各个新闻源获取新闻
    all_new_news = []
    
    # 1. 从 financialjuice 获取新闻（不使用其自己的缓存）
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
    
    # 合并并去重
    if use_cache and cached_news:
        merged_news = merge_and_deduplicate_news(all_new_news, cached_news)
    else:
        # 如果没有缓存，只对新新闻去重
        news_dict = {}
        for item in all_new_news:
            key = get_news_key(item)
            news_dict[key] = item
        merged_news = list(news_dict.values())
        merged_news = sorted(merged_news, key=lambda x: x.get("datetime", ""), reverse=True)
    
    # 保存到缓存文件
    if use_cache:
        save_cached_news(merged_news)
        print(f"已保存 {len(merged_news)} 条新闻到缓存文件")
    
    return merged_news


if __name__ == "__main__":
    news_list = fetch_latest_news()
    print(f"\n总共获取到 {len(news_list)} 条新闻（已去重）\n")
    for n in news_list[:20]:  # 打印前 20 条
        source = n.get("source", "unknown")
        print(f"[{source}] {n.get('datetime', '')} - {n.get('title', '')[:60]}...")


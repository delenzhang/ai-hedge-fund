"""
News Manager agent.

这个模块包含新闻管理代理，用于从大量新闻中筛选出与特定股票相关的新闻。
每次执行时会更新新闻缓存，并使用近半年的新闻进行筛选。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

from src.graph.state import AgentState
from src.utils.llm import call_llm
from src.utils.progress import progress
from src.agents.contexts.news_manager import get_news_filter_prompt_messages
from src.news.index import fetch_latest_news, load_cached_news


# 定义新闻项数据模型
class NewsItem(BaseModel):
    """新闻项数据模型"""
    datetime: str
    title: str
    title_cn: str = ""  # 标题中文翻译
    raw_time: str = ""
    labels: list = []
    news_id: int = 0
    url: str = ""
    relevance_reason: str = ""  # 入选理由（仅中文）


# 定义筛选后的新闻输出模型
class FilteredNewsOutput(BaseModel):
    """筛选后的新闻输出模型"""
    news: List[NewsItem] = []


def get_recent_news_from_cache(days: int = 180) -> list[dict]:
    """
    从缓存文件中获取近指定天数的新闻
    
    参数:
        days: 要获取的天数，默认180天（约半年）
    
    返回:
        近指定天数的新闻列表
    """
    # 先更新新闻缓存
    print("正在更新新闻缓存...")
    fetch_latest_news()
    
    # 从缓存文件加载所有新闻
    all_news = load_cached_news()
    
    if not all_news:
        print("警告: 缓存文件中没有新闻数据")
        return []
    
    # 计算截止日期（days 天前）
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 筛选近指定天数的新闻
    recent_news = []
    for news_item in all_news:
        try:
            # 解析新闻日期时间
            news_datetime_str = news_item.get("datetime", "")
            if not news_datetime_str:
                continue
            
            # 解析日期时间字符串，格式: "2025-11-19 15:38"
            news_datetime = datetime.strptime(news_datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果新闻日期在截止日期之后，则包含
            if news_datetime >= cutoff_date:
                recent_news.append(news_item)
        except Exception as e:
            # 如果解析失败，跳过该新闻
            continue
    
    print(f"从缓存中获取到 {len(recent_news)} 条近 {days} 天的新闻（共 {len(all_news)} 条）")
    return recent_news


def filter_news_for_tickers(
    tickers: list[str],
    agent_id: str,
    state: AgentState,
    days: int = 180,
    use_progress: bool = True,
) -> dict[str, list[dict]]:
    """
    使用大模型为每个股票筛选相关新闻
    每次执行时会先更新新闻缓存，然后使用近指定天数的新闻进行筛选
    
    参数:
        tickers: 股票代码列表，格式: ["PYPL", "BABA", ...]
        agent_id: 代理 ID，用于进度跟踪和模型配置
        state: AgentState 对象，包含模型配置等信息
        days: 要筛选的新闻天数，默认180天（约半年）
        use_progress: 是否使用进度跟踪，默认 True
    
    返回:
        按股票分组的筛选后新闻字典，格式: {"PYPL": [相关新闻列表], "BABA": [相关新闻列表], ...}
    """
    if not tickers:
        return {}
    
    # 获取近指定天数的新闻（会自动更新缓存）
    recent_news = get_recent_news_from_cache(days=days)
    
    if not recent_news:
        print("警告: 没有可用的新闻数据")
        return {ticker: [] for ticker in tickers}
    
    # 构建新闻筛选的 prompt 模板
    template = ChatPromptTemplate.from_messages(get_news_filter_prompt_messages())
    
    # 为每个股票筛选新闻
    filtered_news_by_ticker = {}
    
    for ticker in tickers:
        if use_progress:
            progress.update_status(agent_id, ticker, f"筛选 {ticker} 相关新闻")
        
        # 构建 prompt 数据
        prompt_data = {
            "ticker": ticker,
            "all_news": json.dumps(recent_news, separators=(",", ":"), ensure_ascii=False),
        }
        
        # 生成 prompt
        prompt = template.invoke(prompt_data)
        
        # 调用 LLM 筛选新闻
        try:
            result = call_llm(
                prompt=prompt,
                pydantic_model=FilteredNewsOutput,
                agent_name=agent_id,
                state=state,
                default_factory=lambda: FilteredNewsOutput(news=[]),
            )
            
            # 转换为字典列表，并确保包含必要字段
            filtered_news = []
            for item in result.news:
                news_dict = item.model_dump()
                # 如果没有中文翻译，使用原标题
                if not news_dict.get("title_cn"):
                    news_dict["title_cn"] = news_dict.get("title", "")
                # 如果没有入选理由，添加默认理由
                if not news_dict.get("relevance_reason"):
                    news_dict["relevance_reason"] = "相关新闻"
                filtered_news.append(news_dict)
            
            filtered_news_by_ticker[ticker] = filtered_news
            
            # 打印筛选结果，包含入选理由
            print(f"{ticker} 筛选出 {len(filtered_news)} 条相关新闻：")
            for idx, news in enumerate(filtered_news, 1):
                title = news.get("title", "无标题")
                title_cn = news.get("title_cn", "")
                reason = news.get("relevance_reason", "相关新闻")
                if title_cn and title_cn != title:
                    print(f"  {idx}. {title[:50]}... / {title_cn[:50]}...")
                else:
                    print(f"  {idx}. {title[:60]}...")
                print(f"     入选理由: {reason}")
        except Exception as e:
            print(f"警告: 为 {ticker} 筛选新闻时出错: {e}")
            filtered_news_by_ticker[ticker] = []
    
    return filtered_news_by_ticker


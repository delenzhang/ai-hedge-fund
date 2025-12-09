"""
News Manager agent.

这个模块包含新闻管理代理，用于从大量新闻中筛选出与特定股票相关的新闻。
优化版本：按股票维度存储筛选后的新闻，只对新新闻进行筛选，减少 token 消耗。
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

from src.graph.state import AgentState
from src.utils.llm import call_llm
from src.utils.progress import progress
from src.agents.contexts.news_manager import get_news_filter_prompt_messages
from src.news.index import get_news_key, fetch_latest_news


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


# 筛选后新闻的缓存目录
FILTERED_NEWS_CACHE_DIR = Path(".cache/news_manager/filtered")


def load_filtered_news_for_ticker(ticker: str) -> List[dict]:
    """
    从缓存文件中加载指定股票的筛选后新闻
    
    参数:
        ticker: 股票代码
    
    返回:
        该股票的筛选后新闻列表
    """
    cache_file = FILTERED_NEWS_CACHE_DIR / f"{ticker}.json"
    
    if not cache_file.exists():
        return []
    
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        print(f"警告: 无法读取 {ticker} 的筛选后新闻缓存: {e}")
        return []


def save_filtered_news_for_ticker(ticker: str, news_list: List[dict]):
    """
    保存指定股票的筛选后新闻到缓存文件
    
    注意：
    - 筛选后的新闻只保存在 filtered/{TICKER}.json
    - 一个新闻可以出现在多个股票的筛选结果中，但同一股票内不会重复
    
    参数:
        ticker: 股票代码
        news_list: 筛选后的新闻列表（已去重）
    """
    try:
        # 确保目录存在
        FILTERED_NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        cache_file = FILTERED_NEWS_CACHE_DIR / f"{ticker}.json"
        
        # 保存到文件
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(news_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"警告: 无法保存 {ticker} 的筛选后新闻缓存: {e}")


def get_processed_news_keys(filtered_news: List[dict]) -> Set[str]:
    """
    获取已处理新闻的唯一标识集合
    
    参数:
        filtered_news: 筛选后的新闻列表
    
    返回:
        新闻唯一标识的集合
    """
    return {get_news_key(item) for item in filtered_news}


def deduplicate_news_list(news_list: List[dict]) -> List[dict]:
    """
    对新闻列表进行去重（同一股票内去重）
    
    参数:
        news_list: 新闻列表
    
    返回:
        去重后的新闻列表，按时间倒序排序
    """
    # 创建以唯一标识为键的字典
    news_dict = {}
    
    for item in news_list:
        key = get_news_key(item)
        # 如果已存在，保留最新的（后添加的会覆盖）
        news_dict[key] = item
    
    # 转换回列表并按日期倒序排序
    deduplicated_list = list(news_dict.values())
    deduplicated_list = sorted(deduplicated_list, key=lambda x: x.get("datetime", ""), reverse=True)
    
    return deduplicated_list


def filter_news_by_days(news_list: List[dict], days: int) -> List[dict]:
    """
    过滤出近N天的新闻（不修改缓存，只用于返回）
    
    参数:
        news_list: 新闻列表
        days: 要保留的天数
    
    返回:
        近N天的新闻列表
    """
    if not news_list:
        return []
    
    # 计算截止日期
    cutoff_date = datetime.now() - timedelta(days=days)
    
    filtered_news = []
    for news_item in news_list:
        try:
            # 解析新闻日期时间
            news_datetime_str = news_item.get("datetime", "")
            if not news_datetime_str:
                continue
            
            # 解析日期时间字符串，格式: "2025-11-19 15:38"
            news_datetime = datetime.strptime(news_datetime_str, "%Y-%m-%d %H:%M")
            
            # 如果新闻日期在截止日期之后，则包含
            if news_datetime >= cutoff_date:
                filtered_news.append(news_item)
        except Exception as e:
            # 如果解析失败，跳过该新闻
            continue
    
    return filtered_news


def merge_and_deduplicate_filtered_news(
    new_filtered_news: List[dict],
    cached_filtered_news: List[dict]
) -> List[dict]:
    """
    合并新筛选的新闻和历史筛选的新闻，并去重
    
    注意：
    - 筛选后的新闻只保存在 filtered/{TICKER}.json
    - 同一新闻可以出现在多个股票的筛选结果中（如 BABA 和 INTC）
    - 但在同一个股票的筛选结果中，不会出现重复的新闻
    
    参数:
        new_filtered_news: 新筛选的新闻列表（可能包含重复）
        cached_filtered_news: 历史筛选的新闻列表
    
    返回:
        去重后的新闻列表，按时间倒序排序
    """
    # 首先对新筛选的新闻进行去重（防止 LLM 返回重复）
    new_filtered_news = deduplicate_news_list(new_filtered_news)
    
    # 创建以唯一标识为键的字典
    news_dict = {}
    
    # 首先添加历史筛选的新闻
    for item in cached_filtered_news:
        key = get_news_key(item)
        news_dict[key] = item
    
    # 然后添加新筛选的新闻（会覆盖相同标识的旧新闻）
    for item in new_filtered_news:
        key = get_news_key(item)
        news_dict[key] = item
    
    # 转换回列表并按日期倒序排序
    merged_list = list(news_dict.values())
    merged_list = sorted(merged_list, key=lambda x: x.get("datetime", ""), reverse=True)
    
    return merged_list


def get_recent_news_for_filtering(
    ticker: str, 
    days: int = 180, 
    all_news: list[dict] | None = None
) -> list[dict]:
    """
    获取指定股票需要筛选的新闻（排除已筛选的）
    
    注意：
    - 实时从新闻源获取最新新闻，不存储缓存
    - 排除该股票已经筛选过的新闻
    
    参数:
        ticker: 股票代码
        days: 要获取的天数，默认180天（约半年）
        all_news: 可选的新闻列表，如果提供则使用，否则从新闻源获取
    
    返回:
        需要筛选的新闻列表
    """
    # 如果未提供新闻列表，则从新闻源获取
    if not all_news:
        print("警告: 没有获取到新闻数据")
        return None
    
    # 获取该股票已筛选的新闻标识
    cached_filtered_news = load_filtered_news_for_ticker(ticker)
    processed_keys = get_processed_news_keys(cached_filtered_news)
    
    # 计算截止日期（days 天前）
    cutoff_date = datetime.now() - timedelta(days=days)
    
    # 筛选近指定天数且未筛选的新闻
    recent_news = []
    for news_item in all_news:
        # 跳过已筛选的新闻
        key = get_news_key(news_item)
        if key in processed_keys:
            continue
        
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
    
    print(f"{ticker}: 获取到 {len(recent_news)} 条需要筛选的新闻（共 {len(all_news)} 条，已筛选 {len(processed_keys)} 条）")
    return recent_news


def filter_news_for_tickers(
    tickers: list[str],
    agent_id: str,
    state: AgentState,
    days: int = 180,
    use_progress: bool = True,
) -> dict[str, list[dict]]:
    """
    使用大模型为每个股票筛选相关新闻（优化版本）
    
    优化策略：
    1. 只调用一次 fetch_latest_news()，多个股票共享同一份新闻数据
    2. 按股票维度存储筛选后的新闻（保存在 filtered/{TICKER}.json）
    3. 只对新新闻进行大模型筛选，减少 token 消耗
    4. 自动合并历史筛选结果和新筛选结果，并去重
    
    重要说明：
    - 实时从新闻源获取最新新闻，不存储原始新闻缓存
    - 筛选后的新闻只保存在 .cache/news_manager/filtered/{TICKER}.json
    - 一个新闻可以同时出现在多个股票的筛选结果中（如 BABA 和 INTC）
    - 但在同一个股票的筛选结果中，不会出现重复的新闻
    - 每个股票独立筛选，只排除自己已筛选过的新闻
    
    参数:
        tickers: 股票代码列表，格式: ["PYPL", "BABA", ...]
        agent_id: 代理 ID，用于进度跟踪和模型配置
        state: AgentState 对象，包含模型配置等信息
        days: 要筛选的新闻天数，默认180天（约半年）
        use_progress: 是否使用进度跟踪，默认 True
    
    返回:
        按股票分组的筛选后新闻字典，格式: {"PYPL": [相关新闻列表], "BABA": [相关新闻列表], ...}
        返回的新闻包含历史筛选结果和新筛选结果的合并，已去重
    """
    if not tickers:
        return {}
    
    # 构建新闻筛选的 prompt 模板
    template = ChatPromptTemplate.from_messages(get_news_filter_prompt_messages())
    
    # 优化：只调用一次 fetch_latest_news，多个股票共享
    print("正在从新闻源获取最新新闻...")
    all_news = fetch_latest_news()
    if not all_news:
        print("警告: 没有获取到新闻数据，返回空结果")
        # 从缓存中加载并过滤出近N天的新闻
        result = {}
        for ticker in tickers:
            cached_news = load_filtered_news_for_ticker(ticker)
            recent_news = filter_news_by_days(cached_news, days=days)
            result[ticker] = recent_news
        return result
    
    print(f"获取到 {len(all_news)} 条新闻，开始为 {len(tickers)} 个股票筛选...")
    
    # 为每个股票筛选新闻
    filtered_news_by_ticker = {}
    
    for ticker in tickers:
        if use_progress:
            progress.update_status(agent_id, ticker, f"筛选 {ticker} 相关新闻")
        
        # 1. 加载该股票的历史筛选结果
        cached_filtered_news = load_filtered_news_for_ticker(ticker)
        
        print(f"{ticker}: 历史筛选结果 {len(cached_filtered_news)} 条")
        
        # 2. 获取需要筛选的新闻（使用共享的新闻列表，排除已筛选的）
        new_news = get_recent_news_for_filtering(ticker, days=days, all_news=all_news)
        
        if not new_news:
            print(f"{ticker}: 没有新新闻需要筛选")
            # 从历史筛选结果中过滤出近N天的新闻用于返回（不修改缓存）
            recent_cached_news = filter_news_by_days(cached_filtered_news, days=days)
            filtered_news_by_ticker[ticker] = recent_cached_news
            print(f"{ticker}: 缓存中保留 {len(cached_filtered_news)} 条，返回近{days}天 {len(recent_cached_news)} 条")
            continue
        
        # 3. 对新新闻进行大模型筛选
        new_filtered_news = []
        
        # 构建 prompt 数据（只包含新新闻）
        prompt_data = {
            "ticker": ticker,
            "news_count": len(new_news),
            "all_news": json.dumps(new_news, separators=(",", ":"), ensure_ascii=False),
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
            
            # 创建原始新闻的查找字典（用于匹配 source 字段）
            original_news_dict = {}
            for news in new_news:
                key = get_news_key(news)
                original_news_dict[key] = news
            
            # 转换为字典列表，并确保包含必要字段
            for item in result.news:
                news_dict = item.model_dump()
                # 如果没有中文翻译，使用原标题
                if not news_dict.get("title_cn"):
                    news_dict["title_cn"] = news_dict.get("title", "")
                # 如果没有入选理由，添加默认理由
                if not news_dict.get("relevance_reason"):
                    news_dict["relevance_reason"] = "相关新闻"
                
                # 从原始新闻中恢复 source 字段
                news_key = get_news_key(news_dict)
                if news_key in original_news_dict:
                    original_news = original_news_dict[news_key]
                    if "source" in original_news:
                        news_dict["source"] = original_news["source"]
                
                new_filtered_news.append(news_dict)
            
            print(f"{ticker}: 从 {len(new_news)} 条新新闻中筛选出 {len(new_filtered_news)} 条相关新闻")
            
            # 打印新筛选的新闻
            if new_filtered_news:
                print(f"{ticker} 新筛选的新闻：")
                for idx, news in enumerate(new_filtered_news, 1):
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
        
        # 4. 合并历史筛选结果和新筛选结果，并去重
        merged_filtered_news = merge_and_deduplicate_filtered_news(
            new_filtered_news, cached_filtered_news
        )
        
        # 5. 保存合并后的结果到缓存文件（保留所有历史新闻，不清理缓存）
        save_filtered_news_for_ticker(ticker, merged_filtered_news)
        
        # 6. 过滤出近N天的新闻用于返回（不修改缓存，只用于返回）
        recent_filtered_news = filter_news_by_days(merged_filtered_news, days=days)
        
        # 7. 返回近N天的新闻（缓存中保留所有历史新闻）
        filtered_news_by_ticker[ticker] = recent_filtered_news
        
        print(f"{ticker}: 缓存中保留 {len(merged_filtered_news)} 条（历史 {len(cached_filtered_news)} 条 + 新增 {len(new_filtered_news)} 条，已去重），返回近{days}天 {len(recent_filtered_news)} 条")
    
    return filtered_news_by_ticker


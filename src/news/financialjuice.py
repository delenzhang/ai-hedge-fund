# https://www.financialjuice.com/home
import requests
import json
import re
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote

HOME_URL = "https://www.financialjuice.com/home"
API_URL = "https://live.financialjuice.com/FJService.asmx/Startup"

# 缓存文件路径
CACHE_DIR = Path(".cache/news")
CACHE_FILE = CACHE_DIR / "financialjuice.json"

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
    "cache-control": "no-cache",
    "content-type": "application/json; charset=utf-8",
    "origin": "https://www.financialjuice.com",
    "pragma": "no-cache",
    "referer": "https://www.financialjuice.com/",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}


def extract_info_parameter(html_content: str) -> str:
    """
    从首页 HTML 中提取 info 参数
    尝试从 JavaScript 代码或 API 调用中提取
    """
    # 方法1: 从 JavaScript 中查找 Startup 调用（URL 编码格式）
    pattern = r'Startup\?info=([^"&\']+)'
    match = re.search(pattern, html_content)
    if match:
        info_param = match.group(1)
        # URL 解码
        try:
            return unquote(info_param)
        except Exception:
            return info_param
    
    # 方法2: 查找未编码的 info 参数（在 JavaScript 变量中）
    pattern = r'info["\']?\s*[:=]\s*["\']([^"\']+)["\']'
    match = re.search(pattern, html_content)
    if match:
        return match.group(1)
    
    # 方法3: 查找长加密字符串（Base64 格式，通常以 EAAA 开头）
    pattern = r'(EAAA[A-Za-z0-9+/=]{200,})'
    match = re.search(pattern, html_content)
    if match:
        return match.group(1)
    
    # 如果找不到，返回空字符串，使用默认参数
    return ""


def parse_datetime_from_api(date_str: str) -> str:
    """
    从 API 返回的 DatePublished 字段解析日期时间
    格式: "2025-11-19T16:27:21.19" -> "2025-11-19 16:27"
    """
    try:
        # 移除毫秒部分
        if '.' in date_str:
            date_str = date_str.split('.')[0]
        dt = datetime.fromisoformat(date_str.replace('T', ' '))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_str


def load_cached_news() -> list:
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


def save_cached_news(news_list: list):
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


def merge_news(new_news: list, cached_news: list) -> list:
    """
    合并新新闻和缓存新闻
    使用 news_id 作为唯一标识，如果 news_id 为 0 或不存在，则使用 title + datetime 作为标识
    新新闻优先，但保留缓存中已有的新闻
    """
    # 创建以唯一标识为键的字典
    news_dict = {}
    
    def get_news_key(item):
        """获取新闻的唯一标识键"""
        news_id = item.get("news_id", 0)
        if news_id:
            return f"id_{news_id}"
        # 如果没有 news_id，使用 title + datetime 作为标识
        title = item.get("title", "")
        datetime_str = item.get("datetime", "")
        return f"title_{title}_{datetime_str}"
    
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


def fetch_latest_news(use_cache: bool = True):
    """
    从 FinancialJuice API 获取最新新闻 (倒序)
    返回结构：
       [
          { "datetime": "2025-11-19 15:38", "title": "...", "raw_time": "15:38 Nov 19" },
          ...
       ]
    注意：year 使用执行日期当天的年份
    
    参数:
        use_cache: 是否使用缓存，默认为 True。如果为 True，会与缓存文件对比并合并数据。
    """
    # 加载缓存数据
    cached_news = []
    if use_cache:
        cached_news = load_cached_news()
    # 首先访问首页获取 info 参数
    try:
        home_resp = requests.get(HOME_URL, headers=HEADERS, timeout=10)
        home_resp.raise_for_status()
        info_param = extract_info_parameter(home_resp.text)
    except Exception as e:
        print(f"警告: 无法从首页获取 info 参数: {e}")
        info_param = ""
    
    # 构建 API 请求参数
    # 如果 info 参数为空，使用默认值（从用户提供的 curl 中提取）
    if not info_param:
        # 使用用户提供的默认 info 参数（可能需要定期更新）
        info_param = "EAAAALAMFaG/tFeW5sRHRmSfJQm3RPZTgXYBiVABf1d1vpV9YVqfWPybhJmhUlGtassoaWDhyzv2CcWPgIv8Hp4zlqQoZeYY1kAbLZBVU6bYSJbSTuQ8Lc85uchQf5aTSHbclLXrPhVf4M11U3QM8tSAK30ylpyjRmn3NvSsCNHPeKO4cdZdohPia1AihxdNoc9eR8p+z6/IwL9SH4S2olJ6A7Ny4+rvOdhidFVo3SSN0ywgYu0WXBxAjBEMJCgV/vDH+er4GLJ/6RBdzP1vrRfchryNPPGbKTD5+rKAUUxYHV5nP5IGmaPUbviz4XHFLNtqVg=="
    
    # info 参数需要被双引号包裹并 URL 编码
    info_value = f'"{info_param}"'
    
    params = {
        "info": info_value,
        "TimeOffset": "8",
        "tabID": "0",
        "oldID": "0",
        "TickerID": "0",
        "FeedCompanyID": "0",
        "strSearch": "",
        "extraNID": "0"
    }
    
    # 调用 API
    try:
        api_resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
        api_resp.raise_for_status()
        
        # 解析响应
        response_data = api_resp.json()
        
        # 响应中的 d 字段是字符串化的 JSON
        if "d" in response_data:
            news_data = json.loads(response_data["d"])
        else:
            news_data = response_data
        
        items = []
        
        # 提取新闻列表
        if "News" in news_data and isinstance(news_data["News"], list):
            for news_item in news_data["News"]:
                title = news_item.get("Title", "Unknown")
                posted_long = news_item.get("PostedLong", "")
                date_published = news_item.get("DatePublished", "")
                
                # 优先使用 DatePublished，如果没有则使用 PostedLong
                if date_published:
                    formatted_dt = parse_datetime_from_api(date_published)
                elif posted_long:
                    # 使用原来的解析方法，year 使用执行日期当天的年份
                    year = datetime.now().year
                    try:
                        dt = datetime.strptime(f"{posted_long} {year}", "%H:%M %b %d %Y")
                        formatted_dt = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        formatted_dt = posted_long
                else:
                    formatted_dt = ""
                
                items.append({
                    "datetime": formatted_dt,
                    "title": title,
                    "raw_time": posted_long,
                    "labels": news_item.get("Labels", []),
                    "news_id": news_item.get("NewsID", 0),
                    "url": news_item.get("EURL", ""),
                })
        
        # 以日期倒序排序（最新时间在前）
        items = sorted(items, key=lambda x: x["datetime"], reverse=True)
        
        # 与缓存数据合并
        if use_cache and cached_news:
            items = merge_news(items, cached_news)
        
        # 保存到缓存文件
        if use_cache:
            save_cached_news(items)
        
        return items
        
    except Exception as e:
        print(f"错误: 无法从 API 获取新闻: {e}")
        # 如果 API 失败，返回缓存数据
        if use_cache and cached_news:
            return cached_news
        return []


if __name__ == "__main__":
    news_list = fetch_latest_news()
    for n in news_list[:15]:  # 打印前 15 条
        print(n["datetime"], "-", n["title"])

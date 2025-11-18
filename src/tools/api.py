import datetime
import json
import os
import pandas as pd
import requests
import time
from decimal import Decimal
from longport.openapi import TradeSessions, Period, AdjustType

from src.data.cache import get_cache
from src.data.models import (
    CompanyNews,
    CompanyNewsResponse,
    FinancialMetrics,
    FinancialMetricsResponse,
    Price,
    PriceResponse,
    LineItem,
    LineItemResponse,
    InsiderTrade,
    InsiderTradeResponse,
    CompanyFactsResponse,
)

from src.tools.longbridge import _get_longbridge_ctx

# Global cache instance
_cache = get_cache()

def _period_to_minutes(period: Period) -> int:
    """
    将 Period 枚举转换为分钟数。
    
    Args:
        period: Period 枚举值
        
    Returns:
        int: 对应的分钟数
    """
    # 使用 if-elif 语句来避免 Period 作为字典键的问题
    if period == Period.Min_1:
        return 1
    elif period == Period.Min_2:
        return 2
    elif period == Period.Min_3:
        return 3
    elif period == Period.Min_5:
        return 5
    elif period == Period.Min_10:
        return 10
    elif period == Period.Min_15:
        return 15
    elif period == Period.Min_20:
        return 20
    elif period == Period.Min_30:
        return 30
    elif period == Period.Min_45:
        return 45
    elif period == Period.Min_60:
        return 60
    elif period == Period.Min_120:
        return 120
    elif period == Period.Min_180:
        return 180
    elif period == Period.Min_240:
        return 240
    elif period == Period.Day:
        return 1440  # 1天 = 24 * 60 分钟
    elif period == Period.Week:
        return 10080  # 1周 = 7 * 24 * 60 分钟
    elif period == Period.Month:
        return 43200  # 1月 ≈ 30 * 24 * 60 分钟
    elif period == Period.Quarter:
        return 129600  # 1季度 ≈ 90 * 24 * 60 分钟
    elif period == Period.Year:
        return 525600  # 1年 ≈ 365 * 24 * 60 分钟
    else:
        return 60  # 默认返回60分钟

def _make_api_request(url: str, headers: dict, method: str = "GET", json_data: dict = None, max_retries: int = 3) -> requests.Response:
    """
    Make an API request with rate limiting handling and moderate backoff.
    
    Args:
        url: The URL to request
        headers: Headers to include in the request
        method: HTTP method (GET or POST)
        json_data: JSON data for POST requests
        max_retries: Maximum number of retries (default: 3)
    
    Returns:
        requests.Response: The response object
    
    Raises:
        Exception: If the request fails with a non-429 error
    """
    for attempt in range(max_retries + 1):  # +1 for initial attempt
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=json_data)
        else:
            response = requests.get(url, headers=headers)
        
        if response.status_code == 429 and attempt < max_retries:
            # Linear backoff: 60s, 90s, 120s, 150s...
            delay = 60 + (30 * attempt)
            print(f"Rate limited (429). Attempt {attempt + 1}/{max_retries + 1}. Waiting {delay}s before retrying...")
            time.sleep(delay)
            continue
        
        # Return the response (whether success, other errors, or final 429)
        return response

def get_prices(ticker: str, start_date: str, end_date: str, period: Period = Period.Min_60, api_key: str = None) -> list[Price]:
    """
    从缓存或长桥API获取股票价格数据。
    
    首先检查缓存，如果缓存中有数据且符合日期范围，则直接返回。
    如果缓存中没有数据或数据不在指定日期范围内，则从长桥API获取。
    基于period参数来判断是否需要刷新缓存。
    
    Args:
        ticker: 股票代码（不含市场后缀，如 "AAPL"）
        start_date: 开始日期，格式为 "YYYY-MM-DD"
        end_date: 结束日期，格式为 "YYYY-MM-DD"
        period: K线周期，默认为 Period.Min_60（60分钟）
        api_key: API密钥（可选）
        
    Returns:
        list[Price]: 价格数据列表，每个元素包含 open, close, high, low, volume, time
        
    Raises:
        Exception: 当从长桥API获取数据失败时
    """
    # Get current timestamp
    current_timestamp = time.time()
    print(current_timestamp)
    
    # Convert period to minutes for cache refresh logic
    period_minutes = _period_to_minutes(period)
    # Get period name as string (e.g., "Min_60", "Day", etc.)
    period_str = period.name if hasattr(period, 'name') else str(period).split('.')[-1]
    
    # Create cache key with period
    cache_key = f"{ticker}_{period_str}"
    
    # Check cache first (using period-specific cache key)
    cached_data = _cache.get_prices(ticker, period_str)
    # Get last updated timestamp (using period-specific cache key)
    last_updated_timestamp = _cache.get_last_updated_timestamp("prices", cache_key)
    
    # Get today's date for Period.Day special handling
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check if we need to refresh cache based on period
    # Refresh if:
    # 1. Cache doesn't exist (last_updated_timestamp is None)
    # 2. Last update was more than period_minutes ago
    # 3. For Period.Day: if latest cached data date is not today
    need_refresh = True
    if last_updated_timestamp is not None:
        # Same period (guaranteed by cache key), check if within the period time window
        time_diff_seconds = current_timestamp - last_updated_timestamp
        time_diff_minutes = time_diff_seconds / 60
        # If within period_minutes, no need to refresh (unless Period.Day needs special check)
        need_refresh = time_diff_minutes >= period_minutes
        
        # Special handling for Period.Day: check if latest cached data is today
        if period == Period.Day and cached_data:
            # Find the latest date in cached data
            latest_cached_date = None
            for price in cached_data:
                time_str = price.get("time", "")
                # Extract date part (first 10 characters for "YYYY-MM-DD")
                price_date = time_str[:10] if len(time_str) >= 10 else time_str
                if latest_cached_date is None or price_date > latest_cached_date:
                    latest_cached_date = price_date
            
            # If latest cached date is not today, force refresh
            if latest_cached_date and latest_cached_date < today:
                need_refresh = True
    # else: need_refresh is already True (cache doesn't exist)
    
    # If cache exists and doesn't need refresh, record cache hit and use cache
    if not need_refresh:
        _cache.record_cache_hit("prices")
        if cached_data:
            # Filter cached data by date range
            # Extract date part from time string (handle both "YYYY-MM-DD" and "YYYY-MM-DD HH:MM" formats)
            filtered_data = []
            for price in cached_data:
                time_str = price["time"]
                # Extract date part (first 10 characters for "YYYY-MM-DD")
                price_date = time_str[:10] if len(time_str) >= 10 else time_str
                if start_date <= price_date <= end_date:
                    filtered_data.append(Price(**price))
            return filtered_data
        else:
            # Cache was updated within period but has no data, return empty list
            return []
    
    # If cache needs refresh, fetch from API
    _cache.record_api_call("prices")
    
    try:
        ctx = _get_longbridge_ctx()
        
        # 解析日期
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        
        # 计算交易日数量（每年约252个交易日）
        # 添加缓冲以确保获取到范围内的所有数据
        days_diff = (end_dt - start_dt).days
        # 估算交易日（约为日历日的5/7，每年约252个交易日）
        estimated_trading_days = int(days_diff * 5 / 7) + 100  # 添加安全缓冲
        count = min(estimated_trading_days, 1000)  # 长桥API限制通常为1000根K线
        
        # 为美股代码添加 .US 后缀
        symbol_with_market = f"{ticker}.US"
        
        # 从长桥API获取数据（从结束日期向前查询）
        resp = ctx.candlesticks(
            symbol=symbol_with_market,
            period=period,  # 使用传入的period参数
            adjust_type=AdjustType.ForwardAdjust,  # 前复权
            count=count,
            trade_sessions=TradeSessions.All  # 所有交易时段（盘前、盘中、盘后、隔夜）
        )
        
        # 将 Decimal 转换为 float 并按日期范围过滤
        def convert_decimal(value):
            """将 Decimal 类型转换为 float。"""
            if isinstance(value, Decimal):
                return float(value)
            return value
        
        prices = []
        for candle in resp:
            # 将时间戳格式化为 YYYY-MM-DD HH:MM
            candle_datetime = candle.timestamp.strftime("%Y-%m-%d %H:%M")
            candle_date = candle.timestamp.strftime("%Y-%m-%d")
            
            # 按日期范围过滤（使用日期部分进行比较）
            if start_date <= candle_date <= end_date:
                price = Price(
                    open=convert_decimal(candle.open),
                    close=convert_decimal(candle.close),
                    high=convert_decimal(candle.high),
                    low=convert_decimal(candle.low),
                    volume=int(convert_decimal(candle.volume)),
                    time=candle_datetime
                )
                prices.append(price)
        
        # 按日期升序排序
        prices.sort(key=lambda x: x.time)

        if not prices:
            return []

        # 将结果缓存为字典格式并更新 last_updated_timestamp (使用带period的缓存键)
        _cache.set_prices(ticker, [p.model_dump() for p in prices], period=period_str)
        _cache.set_last_updated_timestamp("prices", cache_key, current_timestamp)
        return prices
        
    except Exception as e:
        raise Exception(f"从长桥API获取数据时出错: {ticker} - {str(e)}")


def get_financial_metrics(
    ticker: str,
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[FinancialMetrics]:
    """Fetch financial metrics from cache or API."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check cache first
    cached_data = _cache.get_financial_metrics(ticker, period)
    cache_key = f"{ticker}_{period}"
    # Use last_updated_date (query date) instead of data's latest date
    latest_cached_date = _cache.get_last_updated_date("financial_metrics", cache_key)
    
    # Check if we need to refresh cache
    # Refresh if cache doesn't exist or last query date is not today
    need_refresh = latest_cached_date is None or latest_cached_date != today
    
    # If cache exists and doesn't need refresh, record cache hit and use cache
    if cached_data and not need_refresh:
        _cache.record_cache_hit("financial_metrics")
    # If cache needs refresh, fetch data up to today from API
    elif need_refresh:
        _cache.record_api_call("financial_metrics")
        headers = {}
        financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
        if financial_api_key:
            headers["X-API-KEY"] = financial_api_key

        # Always fetch data up to today (using today as end_date)
        url = f"https://api.financialdatasets.ai/financial-metrics/?ticker={ticker}&report_period_lte={today}&limit=100&period={period}"
        response = _make_api_request(url, headers)
        if response.status_code != 200:
            raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")

        # Parse response with Pydantic model
        metrics_response = FinancialMetricsResponse(**response.json())
        financial_metrics = metrics_response.financial_metrics

        if financial_metrics:
            # Cache the results (only ticker and period in cache key) and update last_updated_date
            _cache.set_financial_metrics(ticker, period, [m.model_dump() for m in financial_metrics], update_date=today)
            # Update cached_data for filtering
            cached_data = _cache.get_financial_metrics(ticker, period)
    
    # Filter cached data based on end_date and limit
    if not cached_data:
        return []
    
    # Filter by end_date (report_period <= end_date) and limit
    filtered_data = [
        metric for metric in cached_data 
        if metric.get("report_period", "") <= end_date
    ][:limit]
    
    return [FinancialMetrics(**metric) for metric in filtered_data]


def search_line_items(
    ticker: str,
    line_items: list[str],
    end_date: str,
    period: str = "ttm",
    limit: int = 10,
    api_key: str = None,
) -> list[LineItem]:
    """Fetch line items from cache or API."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check cache first (only by ticker and period, no end_date/limit/line_items)
    cached_data = _cache.get_line_items(ticker, period)
    cache_key = f"{ticker}_{period}"
    # Use last_updated_date (query date) instead of data's latest date
    latest_cached_date = _cache.get_last_updated_date("line_items", cache_key)
    
    # Check if we need to refresh cache
    # Refresh if cache doesn't exist or last query date is not today
    need_refresh = latest_cached_date is None or latest_cached_date != today
    
    # If cache exists and doesn't need refresh, record cache hit and use cache
    if cached_data and not need_refresh:
        _cache.record_cache_hit("line_items")
    # If cache needs refresh, fetch all available line items
    elif need_refresh:
        _cache.record_api_call("line_items")
        headers = {}
        financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
        if financial_api_key:
            headers["X-API-KEY"] = financial_api_key

        url = "https://api.financialdatasets.ai/financials/search/line-items"

        # Common line items list for initial fetch (comprehensive list)
        common_line_items = [
            "ebit",  # 息税前利润 / Earnings Before Interest and Taxes
            "interest_expense",  # 利息支出
            "capital_expenditure",  # 资本支出
            "depreciation_and_amortization",  # 折旧和摊销
            "outstanding_shares",  # 流通股数
            "net_income",  # 净利润
            "total_debt",  # 总负债
            "earnings_per_share",  # 每股收益
            "revenue",  # 营业收入
            "book_value_per_share",  # 每股账面价值
            "total_assets",  # 总资产
            "total_liabilities",  # 总负债
            "current_assets",  # 流动资产
            "current_liabilities",  # 流动负债
            "dividends_and_other_cash_distributions",  # 股息和其他现金分配
            "operating_margin",  # 营业利润率
            "debt_to_equity",  # 负债权益比
            "free_cash_flow",  # 自由现金流
            "gross_margin",  # 毛利率
            "research_and_development",  # 研发费用
            "operating_expense",  # 营业费用
            "operating_income",  # 营业利润
            "return_on_invested_capital",  # 投资资本回报率
            "cash_and_equivalents",  # 现金及现金等价物
            "shareholders_equity",  # 股东权益
            "goodwill_and_intangible_assets",  # 商誉和无形资产
            "issuance_or_purchase_of_equity_shares",  # 发行或回购股票
            "gross_profit",  # 毛利润
            "ebitda",  # 息税折旧摊销前利润 / Earnings Before Interest, Taxes, Depreciation and Amortization
            "working_capital",  # 营运资本（流动资产 - 流动负债）   
        ]

        # First fetch: get all common line items with large limit and today's date
        body = {
            "tickers": [ticker],
            "line_items": common_line_items,
            "end_date": today,
            "period": period,
            "limit": 1000,  # Large limit to get all available periods
        }
        response = _make_api_request(url, headers, method="POST", json_data=body)
        
        # If all attempts failed, raise error
        if response.status_code != 200:
            raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")
        
        data = response.json()
        response_model = LineItemResponse(**data)
        search_results = response_model.search_results

        if search_results:
            # Cache all results (only ticker and period in cache key) and update last_updated_date
            _cache.set_line_items(ticker, period, [item.model_dump() for item in search_results], update_date=today)
            # Update cached_data for filtering
            cached_data = _cache.get_line_items(ticker, period)
    
    # Filter cached data based on line_items, end_date, and limit
    if not cached_data:
        return []
    
    filtered_items = []
    for item in cached_data:
        item_report_period = item.get("report_period", "")
        
        # Filter by end_date (report_period <= end_date)
        if item_report_period > end_date:
            continue
        
        # Filter by requested line_items (check if any requested line_item exists in the item)
        item_dict = dict(item)
        has_requested_line_item = False
        for requested_item in line_items:
            # Check if the requested line_item exists as a key in the item
            if requested_item in item_dict and item_dict[requested_item] is not None:
                has_requested_line_item = True
                break
        
        if not has_requested_line_item:
            continue
        
        filtered_items.append(item)
    
    # Sort by report_period descending (newest first)
    filtered_items.sort(key=lambda x: x.get("report_period", ""), reverse=True)
    
    # Apply limit
    filtered_items = filtered_items[:limit]
    
    return [LineItem(**item) for item in filtered_items]


def get_insider_trades(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[InsiderTrade]:
    """Fetch insider trades from cache or API."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check cache first (only by ticker, no start_date/end_date/limit)
    cached_data = _cache.get_insider_trades(ticker)
    # Use last_updated_date (query date) instead of data's latest date
    latest_cached_date = _cache.get_last_updated_date("insider_trades", ticker)
    
    # Calculate one year ago date for default fetch
    one_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    
    # Check if we need to refresh cache
    # Refresh if cache doesn't exist or last query date is not today
    need_refresh = latest_cached_date is None or latest_cached_date != today
    
    # If cache exists and doesn't need refresh, record cache hit and use cache
    if cached_data and not need_refresh:
        _cache.record_cache_hit("insider_trades")
    # If cache needs refresh, fetch default one year of data
    elif need_refresh:
        _cache.record_api_call("insider_trades")
        headers = {}
        financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
        if financial_api_key:
            headers["X-API-KEY"] = financial_api_key

        all_trades = []
        current_end_date = today

        # Fetch one year of data by default
        while True:
            url = f"https://api.financialdatasets.ai/insider-trades/?ticker={ticker}&filing_date_lte={current_end_date}&filing_date_gte={one_year_ago}&limit=1000"

            response = _make_api_request(url, headers)
            if response.status_code != 200:
                raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")

            data = response.json()
            response_model = InsiderTradeResponse(**data)
            insider_trades = response_model.insider_trades

            if not insider_trades:
                break

            all_trades.extend(insider_trades)

            # Check if we got a full page
            if len(insider_trades) < 1000:
                break

            # Update end_date to the oldest filing date from current batch for next iteration
            current_end_date = min(trade.filing_date for trade in insider_trades).split("T")[0]

            # If we've reached or passed the start_date, we can stop
            if current_end_date <= one_year_ago:
                break

        if all_trades:
            # Cache the results (only ticker in cache key) and update last_updated_date
            _cache.set_insider_trades(ticker, [trade.model_dump() for trade in all_trades], update_date=today)
            # Update cached_data for filtering
            cached_data = _cache.get_insider_trades(ticker)
    
    # Filter cached data based on start_date, end_date, and limit
    if not cached_data:
        return []
    
    filtered_trades = []
    for trade in cached_data:
        filing_date = trade.get("filing_date", "")
        # Extract date part if it includes time
        trade_date = filing_date.split("T")[0] if "T" in filing_date else filing_date
        
        # Filter by date range
        if trade_date > end_date:
            continue
        if start_date and trade_date < start_date:
            continue
        
        filtered_trades.append(trade)
    
    # Sort by filing_date descending (newest first) to match cache order
    filtered_trades.sort(key=lambda x: x.get("filing_date", ""), reverse=True)
    
    # Apply limit
    filtered_trades = filtered_trades[:limit]
    
    return [InsiderTrade(**trade) for trade in filtered_trades]


def get_company_news(
    ticker: str,
    end_date: str,
    start_date: str | None = None,
    limit: int = 1000,
    api_key: str = None,
) -> list[CompanyNews]:
    """Fetch company news from cache or API."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check cache first (only by ticker, no start_date/end_date/limit)
    cached_data = _cache.get_company_news(ticker)
    # Use last_updated_date (query date) instead of data's latest date
    latest_cached_date = _cache.get_last_updated_date("company_news", ticker)
    
    # Calculate one year ago date for default fetch
    one_year_ago = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    
    # Check if we need to refresh cache
    # Refresh if cache doesn't exist or last query date is not today
    need_refresh = latest_cached_date is None or latest_cached_date != today
    
    # If cache exists and doesn't need refresh, record cache hit and use cache
    if cached_data and not need_refresh:
        _cache.record_cache_hit("company_news")
    # If cache needs refresh, fetch default one year of data
    elif need_refresh:
        _cache.record_api_call("company_news")
        headers = {}
        financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
        if financial_api_key:
            headers["X-API-KEY"] = financial_api_key

        all_news = []
        current_end_date = today

        # Fetch one year of data by default
        while True:
            url = f"https://api.financialdatasets.ai/news/?ticker={ticker}&end_date={current_end_date}&start_date={one_year_ago}&limit=1000"

            response = _make_api_request(url, headers)
            if response.status_code == 404:
                break;
            if response.status_code != 200:
                raise Exception(f"Error fetching data: {ticker} - {response.status_code} - {response.text}")

            data = response.json()
            response_model = CompanyNewsResponse(**data)
            company_news = response_model.news

            if not company_news:
                break

            all_news.extend(company_news)

            # Check if we got a full page
            if len(company_news) < 1000:
                break

            # Update end_date to the oldest date from current batch for next iteration
            current_end_date = min(news.date for news in company_news).split("T")[0]

            # If we've reached or passed the start_date, we can stop
            if current_end_date <= one_year_ago:
                break

        if all_news:
            # Cache the results (only ticker in cache key) and update last_updated_date
            _cache.set_company_news(ticker, [news.model_dump() for news in all_news], update_date=today)
            # Update cached_data for filtering
            cached_data = _cache.get_company_news(ticker)
    
    # Filter cached data based on start_date, end_date, and limit
    if not cached_data:
        return []
    
    filtered_news = []
    for news in cached_data:
        news_date = news.get("date", "")
        # Extract date part if it includes time
        article_date = news_date.split("T")[0] if "T" in news_date else news_date
        
        # Filter by date range
        if article_date > end_date:
            continue
        if start_date and article_date < start_date:
            continue
        
        filtered_news.append(news)
    
    # Sort by date descending (newest first) to match cache order
    filtered_news.sort(key=lambda x: x.get("date", ""), reverse=True)
    
    # Apply limit
    filtered_news = filtered_news[:limit]
    
    return [CompanyNews(**news) for news in filtered_news]


def get_market_cap(
    ticker: str,
    end_date: str,
    api_key: str = None,
) -> float | None:
    """Fetch market cap from cache or API."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # Check cache first - try to get market cap for the specific end_date
    cached_market_cap = _cache.get_market_cap_by_date(ticker, end_date)
    if cached_market_cap is not None:
        _cache.record_cache_hit("market_cap")
        return cached_market_cap
    
    # Cache doesn't have data for end_date, check if we need to refresh
    latest_cached_date = _cache.get_latest_market_cap_date(ticker)
    need_refresh = latest_cached_date is None or latest_cached_date != today
    
    # If end_date is today, check if we need to refresh cache
    if end_date == today:
        # If cache doesn't exist or latest date is not today, refresh
        if need_refresh:
            _cache.record_api_call("market_cap")
            headers = {}
            financial_api_key = api_key or os.environ.get("FINANCIAL_DATASETS_API_KEY")
            if financial_api_key:
                headers["X-API-KEY"] = financial_api_key

            url = f"https://api.financialdatasets.ai/company/facts/?ticker={ticker}" # free
            response = _make_api_request(url, headers)
            if response.status_code != 200:
                print(f"Error fetching company facts: {ticker} - {response.status_code}")
                return None

            data = response.json()
            response_model = CompanyFactsResponse(**data)
            market_cap = response_model.company_facts.market_cap
            
            # Cache the result
            if market_cap is not None:
                _cache.set_market_cap(ticker, [{"date": today, "market_cap": market_cap}])
            
            return market_cap
        else:
            # Cache exists and latest date is today, but no data for today
            # This shouldn't happen, but return None if it does
            return None
    
    # For historical dates, fetch from financial_metrics API
    financial_metrics = get_financial_metrics(ticker, end_date, api_key=api_key)
    if not financial_metrics:
        return None

    market_cap = financial_metrics[0].market_cap

    if not market_cap:
        return None

    # Cache the result
    _cache.set_market_cap(ticker, [{"date": end_date, "market_cap": market_cap}])
    
    return market_cap


def prices_to_df(prices: list[Price]) -> pd.DataFrame:
    """Convert prices to a DataFrame."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    # 使用 format='mixed' 来处理混合的时间格式（有些只有日期，有些包含时间）
    df["Date"] = pd.to_datetime(df["time"], format='mixed', errors='coerce')
    df.set_index("Date", inplace=True)
    numeric_cols = ["open", "close", "high", "low", "volume"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.sort_index(inplace=True)
    return df


# Update the get_price_data function to use the new functions
def get_price_data(ticker: str, start_date: str, end_date: str, period: Period = Period.Min_60, api_key: str = None) -> pd.DataFrame:
    prices = get_prices(ticker, start_date, end_date, period=period, api_key=api_key)
    return prices_to_df(prices)


def get_fed_rate_cut_expectation(url: str = "https://polymarket.com/event/fed-decision-in-december?tid=1763218927996") -> dict[str, float] | None:
    """
    从 Polymarket 获取美联储降息预期数据。
    
    Args:
        url: Polymarket 事件页面 URL，默认为 12 月美联储决策事件
        
    Returns:
        dict: 包含降息预期的字典，格式为 {
            "cut_25bp": 0.43,  # 降息 25 个基点的概率
            "cut_50bp_or_more": 0.018,  # 降息 50 个基点或更多的概率
            "no_change": 0.54,  # 不变的概率
            "hike": 0.001,  # 加息的概率
            "total_cut_probability": 0.448  # 总降息概率（25bp + 50bp+）
        }
        如果获取失败，返回 None
    """
    try:
        from bs4 import BeautifulSoup
        import re
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = _make_api_request(url, headers, method="GET")
        if response.status_code != 200:
            print(f"无法获取 Polymarket 数据: HTTP {response.status_code}")
            return None
        
        # 尝试从 HTML 中提取数据
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Polymarket 通常使用 JSON-LD 或内联 JSON 来存储市场数据
        # 尝试查找包含市场数据的 script 标签
        scripts = soup.find_all('script', type='application/json')
        market_data = None
        
        for script in scripts:
            try:
                data = json.loads(script.string)
                # 查找包含市场概率的数据结构
                if isinstance(data, dict) and ('market' in str(data).lower() or 'probability' in str(data).lower()):
                    market_data = data
                    break
            except:
                continue
        
        # 如果找不到 JSON 数据，尝试从文本中提取概率信息
        if market_data is None:
            # 查找包含百分比数字的文本
            text = soup.get_text()
            
            # 使用用户提供的具体文案来匹配
            # No change 54%
            # 25 bps decrease 43%
            # 50+ bps decrease 1.8%
            # 25+ bps increase <1%
            
            result = {
                "cut_25bp": 0.0,
                "cut_50bp_or_more": 0.0,
                "no_change": 0.0,
                "hike": 0.0,
                "total_cut_probability": 0.0
            }
            
            # 匹配 "No change 54%" 格式
            no_change_patterns = [
                r'No\s+change\s+(\d+\.?\d*)\s*%',  # "No change 54%"
                r'(\d+\.?\d*)\s*%\s*No\s+change',  # "54% No change"
                r'不变\s+(\d+\.?\d*)\s*%',  # "不变 54%"
            ]
            for pattern in no_change_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result["no_change"] = float(match.group(1)) / 100.0
                    break
            
            # 匹配 "25 bps decrease 43%" 格式
            cut_25_patterns = [
                r'25\s*bps?\s*decrease\s+(\d+\.?\d*)\s*%',  # "25 bps decrease 43%"
                r'(\d+\.?\d*)\s*%\s*25\s*bps?\s*decrease',  # "43% 25 bps decrease"
                r'25\s*基点\s*降息\s+(\d+\.?\d*)\s*%',  # "25 基点 降息 43%"
            ]
            for pattern in cut_25_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result["cut_25bp"] = float(match.group(1)) / 100.0
                    break
            
            # 匹配 "50+ bps decrease 1.8%" 格式
            cut_50_patterns = [
                r'50\+?\s*bps?\s*decrease\s+(\d+\.?\d*)\s*%',  # "50+ bps decrease 1.8%"
                r'(\d+\.?\d*)\s*%\s*50\+?\s*bps?\s*decrease',  # "1.8% 50+ bps decrease"
                r'50\+?\s*基点\s*降息\s+(\d+\.?\d*)\s*%',  # "50+ 基点 降息 1.8%"
            ]
            for pattern in cut_50_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result["cut_50bp_or_more"] = float(match.group(1)) / 100.0
                    break
            
            # 匹配 "25+ bps increase <1%" 或 "<1%" 格式
            hike_patterns = [
                r'25\+?\s*bps?\s*increase\s*<(\d+\.?\d*)\s*%',  # "25+ bps increase <1%"
                r'<(\d+\.?\d*)\s*%\s*25\+?\s*bps?\s*increase',  # "<1% 25+ bps increase"
                r'25\+?\s*bps?\s*increase\s+(\d+\.?\d*)\s*%',  # "25+ bps increase 1%"
                r'(\d+\.?\d*)\s*%\s*25\+?\s*bps?\s*increase',  # "1% 25+ bps increase"
                r'25\+?\s*基点\s*加息\s*<(\d+\.?\d*)\s*%',  # "25+ 基点 加息 <1%"
            ]
            for pattern in hike_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result["hike"] = float(match.group(1)) / 100.0
                    break
            
            # 如果所有值都是 0，说明没有匹配到，返回默认值
            if sum(result.values()) == 0:
                print("警告: 无法从 HTML 中解析 Polymarket 数据，尝试使用默认值")
                return {
                    "cut_25bp": 0.43,
                    "cut_50bp_or_more": 0.018,
                    "no_change": 0.54,
                    "hike": 0.001,
                    "total_cut_probability": 0.448
                }
            
            result["total_cut_probability"] = result["cut_25bp"] + result["cut_50bp_or_more"]
            return result
        
        # 解析市场数据（这里需要根据实际的 Polymarket 数据结构来调整）
        # 由于 Polymarket 的数据结构可能变化，这里提供一个通用的解析逻辑
        result = {
            "cut_25bp": 0.0,
            "cut_50bp_or_more": 0.0,
            "no_change": 0.0,
            "hike": 0.0,
            "total_cut_probability": 0.0
        }
        
        # 尝试从 market_data 中提取概率
        # 注意：这需要根据实际的 Polymarket API 响应格式来调整
        if isinstance(market_data, dict):
            # 查找包含 "25" 和 "cut" 或 "rate" 的键
            for key, value in market_data.items():
                key_lower = str(key).lower()
                if '25' in key_lower and ('cut' in key_lower or 'rate' in key_lower):
                    if isinstance(value, (int, float)):
                        result["cut_25bp"] = float(value) / 100.0 if value > 1 else float(value)
                elif '50' in key_lower and ('cut' in key_lower or 'rate' in key_lower):
                    if isinstance(value, (int, float)):
                        result["cut_50bp_or_more"] = float(value) / 100.0 if value > 1 else float(value)
                elif 'no' in key_lower and 'change' in key_lower:
                    if isinstance(value, (int, float)):
                        result["no_change"] = float(value) / 100.0 if value > 1 else float(value)
                elif 'hike' in key_lower or 'increase' in key_lower:
                    if isinstance(value, (int, float)):
                        result["hike"] = float(value) / 100.0 if value > 1 else float(value)
        
        result["total_cut_probability"] = result["cut_25bp"] + result["cut_50bp_or_more"]
        
        return result
        
    except Exception as e:
        print(f"获取 Polymarket 降息预期数据时出错: {str(e)}")
        # 返回默认值，避免影响交易决策
        return {
            "cut_25bp": 0.43,
            "cut_50bp_or_more": 0.018,
            "no_change": 0.54,
            "hike": 0.001,
            "total_cut_probability": 0.448
        }

# curl 'https://truthsocial.com/api/v1/accounts/107780257626128497/statuses?with_muted=true&only_media=true' \
#   -H 'accept: application/json, text/plain, */*' \
#   -H 'accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7' \
#   -H 'baggage: sentry-environment=production,sentry-public_key=341951a6e21a4c929c321aa2720401f5,sentry-trace_id=b25538cf86ea4d1c9d35a000661d23fd' \
#   -H 'cache-control: no-cache' \
#   -H 'pragma: no-cache' \
#   -H 'priority: u=1, i' \
#   -H 'referer: https://truthsocial.com/@realDonaldTrump' \
#   -H 'sec-ch-ua: "Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"' \
#   -H 'sec-ch-ua-mobile: ?0' \
#   -H 'sec-ch-ua-platform: "macOS"' \
#   -H 'sec-fetch-dest: empty' \
#   -H 'sec-fetch-mode: cors' \
#   -H 'sec-fetch-site: same-origin' \
#   -H 'sentry-trace: b25538cf86ea4d1c9d35a000661d23fd-9fd1d76e6ef0b69b' \
#   -H 'user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'

import subprocess
import json
import time
import re
import os
import requests
from typing import Optional, Dict, Any

from datetime import datetime, timedelta

def convert_to_beijing_time(utc_time_str):
    # 将 UTC 时间字符串解析为 datetime 对象
    try:
        utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # 尝试不带毫秒的格式
        try:
            utc_time = datetime.strptime(utc_time_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            # 如果都失败，返回原字符串
            return utc_time_str
    # 北京时间比 UTC 时间快 8 小时
    beijing_time = utc_time + timedelta(hours=8)
    # 格式化为北京时间字符串，格式与 financialjuice 一致: "YYYY-MM-DD HH:MM"
    return beijing_time.strftime("%Y-%m-%d %H:%M")

def _get_proxy_config() -> Optional[Dict[str, str]]:
    """获取代理配置"""
    proxy = os.environ.get("SOCKS5_PROXY", "127.0.0.1:1080")
    if not proxy:
        return None
    
    # 支持 SOCKS5 代理
    return {
        'http': f'socks5h://{proxy}',
        'https': f'socks5h://{proxy}'
    }


def fetch_trump_statuses_with_session_cookie():
    """
    方法1: 使用 Session Cookie 获取（推荐）
    
    使用方法：
    1. 在浏览器中登录 Truth Social
    2. 打开开发者工具 (F12)
    3. 在 Application/Storage -> Cookies 中找到 _session_id 或类似的 cookie
    4. 设置环境变量: export TRUTH_SOCIAL_SESSION="your_session_cookie_value"
    """
    session_cookie = os.environ.get("TRUTH_SOCIAL_SESSION")
    if not session_cookie:
        return None
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "referer": "https://truthsocial.com/@realDonaldTrump",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "cookie": f"_session_id={session_cookie}"
    }
    
    try:
        proxies = _get_proxy_config()
        response = requests.get(
            "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses",
            headers=headers,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"警告: Session Cookie 方法失败 (状态码: {response.status_code})")
            return None
    except Exception as e:
        print(f"警告: Session Cookie 方法异常: {e}")
        return None


def fetch_trump_statuses_with_mastodon_api():
    """
    方法2: 尝试使用 Mastodon 公开 API 端点
    Truth Social 基于 Mastodon，可能支持公开时间线
    """
    headers = {
        "accept": "application/json",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    # 尝试多个可能的端点
    endpoints = [
        "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses?limit=20",
        "https://truthsocial.com/api/v1/accounts/107780257626128497",
        "https://truthsocial.com/@realDonaldTrump.rss",  # RSS feed
    ]
    
    proxies = _get_proxy_config()
    
    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, headers=headers, proxies=proxies, timeout=15)
            if response.status_code == 200:
                # 尝试解析为 JSON
                try:
                    data = response.json()
                    if isinstance(data, list) or (isinstance(data, dict) and 'statuses' in data):
                        return data if isinstance(data, list) else data.get('statuses', [])
                except:
                    # 如果不是 JSON，可能是 RSS
                    if 'rss' in endpoint or 'xml' in response.headers.get('content-type', ''):
                        # RSS 解析可以后续添加
                        pass
        except Exception as e:
            continue
    
    return None


def fetch_trump_statuses_with_web_scraping():
    """
    方法3: 网页抓取（如果公开页面存在）
    抓取 Truth Social 的公开页面 HTML
    """
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    }
    
    try:
        proxies = _get_proxy_config()
        response = requests.get(
            "https://truthsocial.com/@realDonaldTrump",
            headers=headers,
            proxies=proxies,
            timeout=30
        )
        
        if response.status_code == 200:
            # 尝试从 HTML 中提取 JSON 数据（很多 SPA 会在 HTML 中嵌入初始数据）
            html = response.text
            
            # 查找可能的 JSON 数据
            # 查找 <script> 标签中的 JSON
            json_patterns = [
                r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
                r'"statuses"\s*:\s*(\[.+?\])',
                r'<script[^>]*>.*?({.*?"statuses".*?}).*?</script>',
            ]
            
            for pattern in json_patterns:
                matches = re.search(pattern, html, re.DOTALL)
                if matches:
                    try:
                        data = json.loads(matches.group(1))
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict) and 'statuses' in data:
                            return data['statuses']
                    except:
                        continue
            
            # 如果找不到 JSON，可以尝试解析 HTML（需要 BeautifulSoup）
            # 这里先返回 None，后续可以扩展
            return None
        else:
            return None
    except Exception as e:
        print(f"警告: 网页抓取方法异常: {e}")
        return None


def fetch_trump_statuses_with_playwright():
    """
    方法5: 使用 Playwright 自动化浏览器（需要安装 playwright）
    
    使用方法：
    1. 安装: pip install playwright && playwright install chromium
    2. 设置环境变量 TRUTH_SOCIAL_EMAIL 和 TRUTH_SOCIAL_PASSWORD（可选，用于自动登录）
    3. 或者手动登录后，Playwright 会保存 cookies
    
    注意：这个方法需要浏览器环境，比较重，但最可靠
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None  # Playwright 未安装
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 尝试访问 API 端点
            response = page.goto(
                "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses",
                wait_until="networkidle",
                timeout=30000
            )
            
            if response and response.status == 200:
                try:
                    data = response.json()
                    browser.close()
                    return data
                except:
                    pass
            
            browser.close()
            return None
    except Exception as e:
        print(f"警告: Playwright 方法异常: {e}")
        return None


def _fetch_trump_statuses_with_curl():
    """
    方法4: 原始 curl 方法（保留作为后备）
    """
    # 获取代理设置
    proxy = os.environ.get("SOCKS5_PROXY", "127.0.0.1:1080")
    
    curl_command = ["curl", "-s"]
    
    # 如果设置了代理，添加代理参数
    if proxy:
        curl_command.extend([
            "--socks5-hostname",
            proxy
        ])
    
    # 添加 URL 和请求头
    curl_command.extend([
        "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses",
        "-H", "accept: application/json, text/plain, */*",
        "-H", "accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "-H", "referer: https://truthsocial.com/@realDonaldTrump",
        "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ])
    
    # 如果设置了 session cookie，添加到请求中
    session_cookie = os.environ.get("TRUTH_SOCIAL_SESSION")
    if session_cookie:
        curl_command.extend(["-H", f"cookie: _session_id={session_cookie}"])
    
    try:
        result = subprocess.run(curl_command, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                if data:  # 确保不是空响应
                    return data
            except json.JSONDecodeError:
                pass  # 静默失败，让其他方法尝试
        return None
    except Exception:
        return None


def fetch_trump_statuses_with_curl():
    """
    获取特朗普的 Truth Social 状态列表（多策略尝试）
    
    按优先级尝试以下方法：
    1. Session Cookie 方法（如果设置了 TRUTH_SOCIAL_SESSION 环境变量）- 推荐
    2. Mastodon 公开 API
    3. 网页抓取
    4. Playwright 自动化浏览器（如果安装了 playwright）
    5. 原始 curl 方法
    
    代理设置：
    - 支持通过环境变量 SOCKS5_PROXY 配置代理（格式: 127.0.0.1:1080）
    
    使用说明：
    ==========
    方法1（推荐）- Session Cookie:
    ----------------------------
    1. 在浏览器中登录 Truth Social (https://truthsocial.com)
    2. 打开开发者工具 (F12 或 Cmd+Option+I)
    3. 进入 Application/Storage -> Cookies -> https://truthsocial.com
    4. 找到 _session_id 或类似的 session cookie
    5. 复制 cookie 值，设置环境变量:
       export TRUTH_SOCIAL_SESSION="your_session_cookie_value"
    
    方法2 - Mastodon API:
    -------------------
    自动尝试，无需配置
    
    方法3 - 网页抓取:
    --------------
    自动尝试，无需配置
    
    方法4 - Playwright (高级):
    ------------------------
    1. 安装: pip install playwright && playwright install chromium
    2. 可选：设置 TRUTH_SOCIAL_EMAIL 和 TRUTH_SOCIAL_PASSWORD 用于自动登录
    3. 或者手动登录一次，Playwright 会保存 cookies
    
    方法5 - Curl:
    ------------
    自动尝试，作为最后的后备方案
    """
    # 方法1: 尝试 Session Cookie（最可靠，推荐）
    result = fetch_trump_statuses_with_session_cookie()
    if result:
        print("✓ 使用 Session Cookie 方法成功获取数据")
        return result
    
    # 方法2: 尝试 Mastodon API
    result = fetch_trump_statuses_with_mastodon_api()
    if result:
        print("✓ 使用 Mastodon API 方法成功获取数据")
        return result
    
    # 方法3: 尝试网页抓取
    result = fetch_trump_statuses_with_web_scraping()
    if result:
        print("✓ 使用网页抓取方法成功获取数据")
        return result
    
    # 方法4: 尝试 Playwright（如果可用）
    result = fetch_trump_statuses_with_playwright()
    if result:
        print("✓ 使用 Playwright 方法成功获取数据")
        return result
    
    # 方法5: 尝试原始 curl（作为最后的后备）
    result = _fetch_trump_statuses_with_curl()
    if result:
        print("✓ 使用 Curl 方法成功获取数据")
        return result
    
    print("警告: 所有获取 Trump 状态的方法都失败了")
    print("提示: 推荐使用方法1（Session Cookie），详见函数文档")
    return None


def fetch_trump_news(limit: int = 50) -> list[dict]:
    """
    获取特朗普的新闻列表
    
    参数:
        limit: 获取的最大数量，默认50条
    
    返回:
        新闻列表，格式与 financialjuice 一致:
        [
            {
                "datetime": "2025-11-19 15:38",
                "title": "...",
                "raw_time": "...",
                "labels": [],
                "news_id": 0,
                "url": "...",
                "source": "trump"  # 标识来源
            },
            ...
        ]
    """
    statuses = fetch_trump_statuses_with_curl()
    if not statuses:
        return []
    
    items = []
    for status in statuses[:limit]:
        content = status.get("content", "").strip()
        if not content:
            continue
        
        # 移除 HTML 标签
        content = re.sub(r'<[^>]+>', '', content)
        
        created_at = status.get("created_at", "")
        if created_at:
            datetime_str = convert_to_beijing_time(created_at)
        else:
            datetime_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 获取媒体附件
        media_attachments = status.get("media_attachments", [])
        url = ""
        if media_attachments:
            url = media_attachments[0].get("url", "") or media_attachments[0].get("preview_url", "")
        
        # 获取状态 ID 作为唯一标识
        status_id = status.get("id", "")
        
        items.append({
            "datetime": datetime_str,
            "title": content[:200] if len(content) > 200 else content,  # 限制标题长度
            "raw_time": created_at,
            "labels": ["Trump", "Truth Social"],
            "news_id": 0,  # 使用 status_id 作为唯一标识
            "url": url,
            "source": "truthsocial",
            "status_id": status_id,  # 用于去重
        })
    
    # 按时间倒序排序
    items = sorted(items, key=lambda x: x["datetime"], reverse=True)
    
    return items

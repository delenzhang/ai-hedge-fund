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
import requests
from lib.deepseek import get_deepseek_response

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

def fetch_trump_statuses_with_curl():
    """获取特朗普的 Truth Social 状态列表"""
    curl_command = [
        "curl",
        "-s",
        "https://truthsocial.com/api/v1/accounts/107780257626128497/statuses", #?with_muted=true&only_media=true
        "-H", "accept: application/json, text/plain, */*",
        "-H", "accept-language: zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7",
        "-H", "baggage: sentry-environment=production,sentry-public_key=341951a6e21a4c929c321aa2720401f5,sentry-trace_id=b25538cf86ea4d1c9d35a000661d23fd",
        "-H", "cache-control: no-cache",
        "-H", "pragma: no-cache",
        "-H", "priority: u=1, i",
        "-H", "referer: https://truthsocial.com/@realDonaldTrump",
        "-H", "sec-ch-ua: \"Google Chrome\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
        "-H", "sec-ch-ua-mobile: ?0",
        "-H", "sec-ch-ua-platform: \"macOS\"",
        "-H", "sec-fetch-dest: empty",
        "-H", "sec-fetch-mode: cors",
        "-H", "sec-fetch-site: same-origin",
        "-H", "sentry-trace: b25538cf86ea4d1c9d35a000661d23fd-9fd1d76e6ef0b69b",
        "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ]
    result = subprocess.run(curl_command, capture_output=True, text=True)
   
    if result.returncode == 0:
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"警告: 无法解析 Trump 状态响应")
            return None
    else:
        print(f"警告: 获取 Trump 状态失败: {result.stderr}")
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
            "source": "trump",
            "status_id": status_id,  # 用于去重
        })
    
    # 按时间倒序排序
    items = sorted(items, key=lambda x: x["datetime"], reverse=True)
    
    return items

import requests

def send_wechat_message(content):
    url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=52bc67b9-b194-4378-af5c-67b0e6103b3c"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # 检查请求是否成功
        print(f"消息发送成功: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")


lastContentTime = ""
def main():
    global lastContentTime  # 声明为全局变量
    while True:
        try:
         
          statuses = fetch_trump_statuses_with_curl()
          if statuses:
              firstContent = statuses[0].get("content", "空")
              targetContent = get_deepseek_response(firstContent)
              media_attachments = statuses[0].get("media_attachments", [])
              urls = [attachment.get("preview_url", '') for attachment in media_attachments]
              createTime = convert_to_beijing_time(statuses[0].get('created_at', ''))
              wecomConten = f"<@delenzhang> 川普在{createTime}发了一条状态:\n {firstContent} \n 翻译: \n {targetContent} \n 媒体地址: {', '.join(urls)}"
              print(f"wecomConten: {wecomConten}, createTime: {createTime}")
              if lastContentTime != createTime:
                  lastContentTime = createTime
                  send_wechat_message(wecomConten)
              else:
                  current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                  print(f"当前时间: {current_time} trump 没有新的状态更新")
          time.sleep(5)
        except KeyboardInterrupt:
            print("\n定时任务已停止")
            break
        except Exception as e:
            print(f"任务执行异常: {str(e)}")
            time.sleep(5)  # 异常后仍保持间隔
            

if __name__ == "__main__":
    main()
# 这个代码是一个简单的Python脚本，用于从Truth Social网站获取特朗普的状态更新。
# 它使用requests库发送HTTP GET请求，并处理响应。
# 你可以根据需要修改URL和参数，以获取不同的信息。
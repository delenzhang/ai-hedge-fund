"""
企业微信消息发送工具

提供企业微信 webhook 消息发送功能
"""
import requests
from typing import Optional


# 默认的企业微信 webhook key
DEFAULT_WEBHOOK_KEY = "52bc67b9-b194-4378-af5c-67b0e6103b3c"


def send_wechat_message(content: str, webhook_key: Optional[str] = None) -> bool:
    """
    发送企业微信消息
    
    参数:
        content: 消息内容
        webhook_key: 企业微信 webhook key，如果不提供则使用默认值
    
    返回:
        是否发送成功
    """
    if webhook_key is None:
        webhook_key = DEFAULT_WEBHOOK_KEY
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
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
        print(f"企业微信消息发送成功")
        return True
    except requests.exceptions.RequestException as e:
        print(f"企业微信消息发送失败: {e}")
        return False


def send_wechat_message_with_key(content: str, webhook_key: str) -> bool:
    """
    使用指定的 webhook key 发送企业微信消息
    
    参数:
        content: 消息内容
        webhook_key: 企业微信 webhook key
    
    返回:
        是否发送成功
    """
    return send_wechat_message(content, webhook_key)


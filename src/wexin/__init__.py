"""
企业微信消息发送模块

提供企业微信 webhook 消息发送功能
"""
from .wechat import send_wechat_message, send_wechat_message_with_key

__all__ = ["send_wechat_message", "send_wechat_message_with_key"]


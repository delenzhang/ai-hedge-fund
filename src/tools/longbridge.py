import os
from pickle import TRUE
from longport.openapi import QuoteContext, Config, Period, AdjustType


def _get_longbridge_ctx() -> QuoteContext:
    """
    初始化并返回单例的 QuoteContext 实例。
    
    从环境变量中读取长桥API配置（LB_APP_KEY, LB_APP_SECRET, LB_ACCESS_TOKEN），
    如果未配置则抛出异常。
    
    Returns:
        QuoteContext: 长桥行情上下文实例
        
    Raises:
        ValueError: 当缺少必要的环境变量配置时
    """
    _longbridge_ctx = None
    if _longbridge_ctx is None:
        app_key = os.getenv('LB_APP_KEY')
        app_secret = os.getenv('LB_APP_SECRET')
        access_token = os.getenv('LB_ACCESS_TOKEN')
        
        if not app_key or not app_secret or not access_token:
            raise ValueError(
                "缺少长桥API配置，请在.env文件中设置以下环境变量：\n"
                "  LB_APP_KEY=你的app_key\n"
                "  LB_APP_SECRET=你的app_secret\n"
                "  LB_ACCESS_TOKEN=你的access_token"
            )
        
        config = Config(app_key=app_key, app_secret=app_secret, access_token=access_token,  enable_overnight=True)
        _longbridge_ctx = QuoteContext(config)
        print(f"✅ 已加载长桥API配置")
    
    return _longbridge_ctx

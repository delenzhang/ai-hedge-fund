poetry run python src/main.py --tickers-all --analysts-all

poetry run python src/main.py --tickers MP --analysts-all

# 项目启动依赖
## 代理
`v2ray run -config ./v2ray_config.json`

# 降息概率获取
https://polymarket.com/event/fed-decision-in-december?tid=1763218927996

# 短线新闻分析 Agent 监控脚本

## 单次运行
```bash
# 只运行一次分析
poetry run python scripts/short_term_news/alert.py --interval 0
```

## 定时运行（前台）
```bash
# 每1小时执行一次（默认）
poetry run python scripts/short_term_news/alert.py

# 自定义间隔（例如每30分钟）
poetry run python scripts/short_term_news/alert.py --interval 30
```

## 后台运行（推荐）
```bash
# 启动后台服务（每1小时执行一次）
cd scripts/short_term_news && ./alert.sh start

# 或者从项目根目录运行
./scripts/short_term_news/alert.sh start

# 停止后台服务
./scripts/short_term_news/alert.sh stop

# 重启后台服务
./scripts/short_term_news/alert.sh restart

# 查看服务状态和日志
./scripts/short_term_news/alert.sh status
```

## 功能说明
- 自动分析消息面对当前持仓的影响
- 检测降息概率重大变化（超过15%）时立即发送风险提醒
- 检测到重要变化时发送企业微信消息提醒
- 日志文件：`logs/short_term_news_agent_alert.log`
- PID文件：`.cache/short_term_news/alert.pid`
- 缓存文件：`.cache/short_term_news/alert.json`
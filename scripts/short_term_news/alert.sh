#!/bin/bash

# 短线新闻分析 Agent 后台运行脚本
# 使用方法: ./alert.sh [start|stop|restart|status]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$PROJECT_ROOT/.cache/short_term_news/alert.pid"
LOG_FILE="$PROJECT_ROOT/logs/short_term_news_agent_alert.log"
SCRIPT_FILE="$SCRIPT_DIR/alert.py"

# 确保缓存目录和日志目录存在
mkdir -p "$PROJECT_ROOT/.cache/short_term_news"
mkdir -p "$PROJECT_ROOT/logs"

# 检查 Python 环境
if ! command -v poetry &> /dev/null; then
    echo "错误: 未找到 poetry，请先安装 poetry"
    exit 1
fi

# 函数：启动服务
start_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo "服务已在运行中 (PID: $PID)"
            return 1
        else
            echo "清理过期的 PID 文件"
            rm -f "$PID_FILE"
        fi
    fi
    
    echo "启动短线新闻分析 Agent 监控服务..."
    cd "$PROJECT_ROOT"
    
    # 第一次执行：立即运行一次分析并输出到日志
    echo "正在执行第一次分析..."
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] =========================================" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动短线新闻分析 Agent 监控服务" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 执行第一次分析..." >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] =========================================" >> "$LOG_FILE"
    
    # 执行一次分析（不循环，只运行一次）
    poetry run python "$SCRIPT_FILE" --interval 0 >> "$LOG_FILE" 2>&1
    FIRST_RUN_EXIT_CODE=$?
    
    if [ $FIRST_RUN_EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 第一次分析完成" >> "$LOG_FILE"
        echo "第一次分析完成"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 警告: 第一次分析失败，退出码: $FIRST_RUN_EXIT_CODE" >> "$LOG_FILE"
        echo "警告: 第一次分析失败，但将继续启动定时服务"
    fi
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 启动定时监控服务（每60分钟执行一次）..." >> "$LOG_FILE"
    
    # 使用 nohup 在后台运行定时服务
    nohup poetry run python "$SCRIPT_FILE" --interval 60 >> "$LOG_FILE" 2>&1 &
    PID=$!
    
    # 等待一下确保进程启动
    sleep 2
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$PID" > "$PID_FILE"
        echo "服务已启动 (PID: $PID)"
        echo "日志文件: $LOG_FILE"
        echo "查看日志: tail -f $LOG_FILE"
        return 0
    else
        echo "服务启动失败，请查看日志: $LOG_FILE"
        return 1
    fi
}

# 函数：停止服务
stop_service() {
    if [ ! -f "$PID_FILE" ]; then
        echo "服务未运行（未找到 PID 文件）"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ! ps -p "$PID" > /dev/null 2>&1; then
        echo "服务未运行（进程不存在）"
        rm -f "$PID_FILE"
        return 1
    fi
    
    echo "停止服务 (PID: $PID)..."
    kill "$PID"
    
    # 等待进程结束
    for i in {1..10}; do
        if ! ps -p "$PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "强制停止服务..."
        kill -9 "$PID"
    fi
    
    rm -f "$PID_FILE"
    echo "服务已停止"
    return 0
}

# 函数：重启服务
restart_service() {
    echo "重启服务..."
    stop_service
    sleep 2
    start_service
}

# 函数：查看状态
status_service() {
    if [ ! -f "$PID_FILE" ]; then
        echo "服务状态: 未运行"
        return 1
    fi
    
    PID=$(cat "$PID_FILE")
    
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "服务状态: 运行中 (PID: $PID)"
        echo "日志文件: $LOG_FILE"
        echo ""
        echo "最近日志:"
        tail -n 20 "$LOG_FILE" 2>/dev/null || echo "无法读取日志文件"
        return 0
    else
        echo "服务状态: 未运行（进程不存在）"
        rm -f "$PID_FILE"
        return 1
    fi
}

# 主逻辑
case "${1:-}" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    *)
        echo "使用方法: $0 {start|stop|restart|status}"
        echo ""
        echo "命令说明:"
        echo "  start   - 启动后台监控服务（每1小时执行一次）"
        echo "  stop    - 停止后台监控服务"
        echo "  restart - 重启后台监控服务"
        echo "  status  - 查看服务状态和日志"
        exit 1
        ;;
esac

exit $?


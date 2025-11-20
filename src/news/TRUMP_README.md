# Truth Social 数据获取方案

由于 Truth Social 现在需要登录才能获取数据，我们提供了多种绕过登录的方法。

## 🎯 推荐方案：Session Cookie（最简单可靠）

### 步骤：

1. **在浏览器中登录 Truth Social**
   - 访问 https://truthsocial.com
   - 使用你的账号登录

2. **获取 Session Cookie**
   - 打开开发者工具：
     - Chrome/Edge: `F12` 或 `Cmd+Option+I` (Mac) / `Ctrl+Shift+I` (Windows)
     - Firefox: `F12` 或 `Cmd+Option+I` (Mac) / `Ctrl+Shift+I` (Windows)
   - 进入 **Application** (Chrome) 或 **Storage** (Firefox) 标签
   - 左侧找到 **Cookies** -> `https://truthsocial.com`
   - 查找名为 `_session_id` 或类似的 cookie（可能是 `_truth_session`、`session` 等）
   - 复制 cookie 的 **Value** 值

3. **设置环境变量**
   ```bash
   # Linux/Mac
   export TRUTH_SOCIAL_SESSION="你复制的cookie值"
   
   # Windows (PowerShell)
   $env:TRUTH_SOCIAL_SESSION="你复制的cookie值"
   
   # Windows (CMD)
   set TRUTH_SOCIAL_SESSION=你复制的cookie值
   ```

4. **永久设置（可选）**
   - Linux/Mac: 添加到 `~/.bashrc` 或 `~/.zshrc`
   - Windows: 通过系统环境变量设置

### 注意事项：
- Cookie 会过期，通常几天到几周不等
- 如果失效，重新执行步骤 1-3 获取新的 cookie
- Cookie 是敏感信息，不要分享给他人

---

## 🔄 其他方案

### 方案2：Mastodon 公开 API
- **状态**: 自动尝试
- **说明**: Truth Social 基于 Mastodon，可能支持公开 API
- **配置**: 无需配置，自动尝试

### 方案3：网页抓取
- **状态**: 自动尝试
- **说明**: 尝试从 HTML 页面提取数据
- **配置**: 无需配置，自动尝试

### 方案4：Playwright 自动化（高级）
- **状态**: 需要安装 Playwright
- **安装**:
  ```bash
  pip install playwright
  playwright install chromium
  ```
- **配置**: 
  - 可选：设置 `TRUTH_SOCIAL_EMAIL` 和 `TRUTH_SOCIAL_PASSWORD` 用于自动登录
  - 或者手动登录一次，Playwright 会保存 cookies
- **优点**: 最可靠，可以处理复杂的登录流程
- **缺点**: 需要浏览器环境，资源消耗较大

### 方案5：Curl（后备）
- **状态**: 自动尝试
- **说明**: 原始 curl 方法，作为最后的后备
- **配置**: 无需配置，自动尝试

---

## 🚀 使用示例

```python
from src.news.trump import fetch_trump_news

# 自动尝试所有可用方法
news = fetch_trump_news(limit=20)

for item in news:
    print(f"{item['datetime']}: {item['title']}")
```

---

## 🔧 代理设置

如果需要使用代理，设置环境变量：

```bash
# Linux/Mac
export SOCKS5_PROXY="127.0.0.1:1080"

# Windows (PowerShell)
$env:SOCKS5_PROXY="127.0.0.1:1080"

# 不使用代理
export SOCKS5_PROXY=""
```

---

## ❓ 常见问题

### Q: 所有方法都失败了怎么办？
A: 
1. 首先尝试方案1（Session Cookie），这是最可靠的方法
2. 检查网络连接和代理设置
3. 确认 Truth Social 网站可以正常访问

### Q: Session Cookie 多久会过期？
A: 通常几天到几周，具体取决于 Truth Social 的设置。如果失效，重新获取即可。

### Q: 可以自动刷新 Cookie 吗？
A: 目前需要手动获取。未来可以考虑使用 Playwright 自动登录来刷新。

### Q: 使用这些方法会违反服务条款吗？
A: 这些方法都是通过公开的 API 端点或网页获取数据，类似于浏览器访问。但请注意遵守 Truth Social 的服务条款和使用频率限制。

---

## 📝 技术说明

代码会自动按优先级尝试以下方法：
1. Session Cookie（如果设置了 `TRUTH_SOCIAL_SESSION`）
2. Mastodon 公开 API
3. 网页抓取
4. Playwright（如果已安装）
5. Curl（后备）

如果某个方法成功，会立即返回结果，不会尝试后续方法。


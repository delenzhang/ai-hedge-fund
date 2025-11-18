import subprocess
import re


def get_fed_rate_cut_expectation() -> dict[str, float] | None:
    """
    从 Polymarket 获取美联储降息预期数据。
    使用 curl --socks5-hostname 命令通过代理获取数据。
    
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
        url = "https://polymarket.com/event/fed-decision-in-december?tid=1763218927996"
        
        # 使用 curl 命令通过 SOCKS5 代理获取数据
        cmd = [
            "curl",
            "--socks5-hostname",
            "127.0.0.1:1080",
            url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        err_msg = {
          "error": "没有降息数据，这个不参考"
        }
        
        if result.returncode != 0:
            print(f"无法获取 Polymarket 数据: curl 返回码 {result.returncode}")
            print(f"错误信息: {result.stderr}")
            return err_msg
        
        html_content = result.stdout
        
        # 从 HTML 文本中提取概率信息
        # 使用正则表达式匹配以下格式：
        # No change 54%
        # 25 bps decrease 43%
        # 50+ bps decrease 1.8%
        # 25+ bps increase <1%
        
        result_dict = {
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
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                result_dict["no_change"] = float(match.group(1)) / 100.0
                break
        
        # 匹配 "25 bps decrease 43%" 格式
        cut_25_patterns = [
            r'25\s*bps?\s*decrease\s+(\d+\.?\d*)\s*%',  # "25 bps decrease 43%"
            r'(\d+\.?\d*)\s*%\s*25\s*bps?\s*decrease',  # "43% 25 bps decrease"
            r'25\s*基点\s*降息\s+(\d+\.?\d*)\s*%',  # "25 基点 降息 43%"
        ]
        for pattern in cut_25_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                result_dict["cut_25bp"] = float(match.group(1)) / 100.0
                break
        
        # 匹配 "50+ bps decrease 1.8%" 格式
        cut_50_patterns = [
            r'50\+?\s*bps?\s*decrease\s+(\d+\.?\d*)\s*%',  # "50+ bps decrease 1.8%"
            r'(\d+\.?\d*)\s*%\s*50\+?\s*bps?\s*decrease',  # "1.8% 50+ bps decrease"
            r'50\+?\s*基点\s*降息\s+(\d+\.?\d*)\s*%',  # "50+ 基点 降息 1.8%"
        ]
        for pattern in cut_50_patterns:
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                result_dict["cut_50bp_or_more"] = float(match.group(1)) / 100.0
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
            match = re.search(pattern, html_content, re.IGNORECASE)
            if match:
                result_dict["hike"] = float(match.group(1)) / 100.0
                break
        
        # 如果所有值都是 0，说明没有匹配到
        if sum(result_dict.values()) == 0:
            print("警告: 无法从 HTML 中解析 Polymarket 数据")
            return err_msg
        
        result_dict["total_cut_probability"] = result_dict["cut_25bp"] + result_dict["cut_50bp_or_more"]
        return result_dict
        
    except subprocess.TimeoutExpired:
        print("获取 Polymarket 数据超时")
        return err_msg
    except Exception as e:
        print(f"获取 Polymarket 降息预期数据时出错: {str(e)}")
        return err_msg


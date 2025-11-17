"""Constants and utilities related to analysts configuration."""

from src.agents import portfolio_manager
from src.agents.aswath_damodaran import aswath_damodaran_agent
from src.agents.ben_graham import ben_graham_agent
from src.agents.bill_ackman import bill_ackman_agent
from src.agents.cathie_wood import cathie_wood_agent
from src.agents.charlie_munger import charlie_munger_agent
from src.agents.fundamentals import fundamentals_analyst_agent
from src.agents.michael_burry import michael_burry_agent
from src.agents.phil_fisher import phil_fisher_agent
from src.agents.peter_lynch import peter_lynch_agent
from src.agents.sentiment import sentiment_analyst_agent
from src.agents.stanley_druckenmiller import stanley_druckenmiller_agent
from src.agents.technicals import technical_analyst_agent
from src.agents.valuation import valuation_analyst_agent
from src.agents.warren_buffett import warren_buffett_agent
from src.agents.rakesh_jhunjhunwala import rakesh_jhunjhunwala_agent
from src.agents.mohnish_pabrai import mohnish_pabrai_agent
from src.agents.news_sentiment import news_sentiment_agent
from src.agents.growth_agent import growth_analyst_agent

# Define analyst configuration - single source of truth
ANALYST_CONFIG = {
    "aswath_damodaran": {
        "display_name": "阿斯沃斯·达摩达兰 / Aswath Damodaran",
        "description": "估值学教父 / The Dean of Valuation",
        "investing_style": "专注于内在价值和财务指标，通过严格的估值分析评估投资机会。 / Focuses on intrinsic value and financial metrics to assess investment opportunities through rigorous valuation analysis.",
        "agent_func": aswath_damodaran_agent,
        "type": "analyst",
        "order": 0,
    },
    "ben_graham": {
        "display_name": "本杰明·格雷厄姆 / Ben Graham",
        "description": "价值投资之父 / The Father of Value Investing",
        "investing_style": "强调安全边际，通过系统化的价值分析投资于基本面强劲但被低估的公司。 / Emphasizes a margin of safety and invests in undervalued companies with strong fundamentals through systematic value analysis.",
        "agent_func": ben_graham_agent,
        "type": "analyst",
        "order": 1,
    },
    "bill_ackman": {
        "display_name": "比尔·阿克曼 / Bill Ackman",
        "description": "激进投资者 / The Activist Investor",
        "investing_style": "通过战略性激进主义和反向投资头寸来影响管理层并释放价值。 / Seeks to influence management and unlock value through strategic activism and contrarian investment positions.",
        "agent_func": bill_ackman_agent,
        "type": "analyst",
        "order": 2,
    },
    "cathie_wood": {
        "display_name": "凯茜·伍德 / Cathie Wood",
        "description": "成长投资女王 / The Queen of Growth Investing",
        "investing_style": "专注于颠覆性创新和增长，投资于引领技术进步和市场颠覆的公司。 / Focuses on disruptive innovation and growth, investing in companies that are leading technological advancements and market disruption.",
        "agent_func": cathie_wood_agent,
        "type": "analyst",
        "order": 3,
    },
    "charlie_munger": {
        "display_name": "查理·芒格 / Charlie Munger",
        "description": "理性思考者 / The Rational Thinker",
        "investing_style": "倡导价值投资，专注于优质企业和通过理性决策实现长期增长。 / Advocates for value investing with a focus on quality businesses and long-term growth through rational decision-making.",
        "agent_func": charlie_munger_agent,
        "type": "analyst",
        "order": 4,
    },
    "michael_burry": {
        "display_name": "迈克尔·伯里 / Michael Burry",
        "description": "大空头反向投资者 / The Big Short Contrarian",
        "investing_style": "进行反向押注，经常做空被高估的市场，并通过深入的基本面分析投资被低估的资产。 / Makes contrarian bets, often shorting overvalued markets and investing in undervalued assets through deep fundamental analysis.",
        "agent_func": michael_burry_agent,
        "type": "analyst",
        "order": 5,
    },
    "mohnish_pabrai": {
        "display_name": "莫尼什·帕伯莱 / Mohnish Pabrai",
        "description": "达多投资者 / The Dhandho Investor",
        "investing_style": "通过基本面分析和安全边际，专注于价值投资和长期增长。 / Focuses on value investing and long-term growth through fundamental analysis and a margin of safety.",
        "agent_func": mohnish_pabrai_agent,
        "type": "analyst",
        "order": 6,
    },
    "peter_lynch": {
        "display_name": "彼得·林奇 / Peter Lynch",
        "description": "十倍股投资者 / The 10-Bagger Investor",
        "investing_style": "使用'买你了解的东西'策略，投资于商业模式易懂且增长潜力强劲的公司。 / Invests in companies with understandable business models and strong growth potential using the 'buy what you know' strategy.",
        "agent_func": peter_lynch_agent,
        "type": "analyst",
        "order": 6,
    },
    "phil_fisher": {
        "display_name": "菲利普·费雪 / Phil Fisher",
        "description": "小道消息投资者 / The Scuttlebutt Investor",
        "investing_style": "强调投资于管理团队强大、产品创新的公司，通过小道消息研究专注于长期增长。 / Emphasizes investing in companies with strong management and innovative products, focusing on long-term growth through scuttlebutt research.",
        "agent_func": phil_fisher_agent,
        "type": "analyst",
        "order": 7,
    },
    "rakesh_jhunjhunwala": {
        "display_name": "拉凯什·君君瓦拉 / Rakesh Jhunjhunwala",
        "description": "印度大牛 / The Big Bull Of India",
        "investing_style": "利用宏观经济洞察投资高增长行业，特别是在新兴市场和国内机会中。 / Leverages macroeconomic insights to invest in high-growth sectors, particularly within emerging markets and domestic opportunities.",
        "agent_func": rakesh_jhunjhunwala_agent,
        "type": "analyst",
        "order": 8,
    },
    "stanley_druckenmiller": {
        "display_name": "斯坦利·德鲁肯米勒 / Stanley Druckenmiller",
        "description": "宏观投资者 / The Macro Investor",
        "investing_style": "专注于宏观经济趋势，通过自上而下的分析对货币、大宗商品和利率进行大额押注。 / Focuses on macroeconomic trends, making large bets on currencies, commodities, and interest rates through top-down analysis.",
        "agent_func": stanley_druckenmiller_agent,
        "type": "analyst",
        "order": 9,
    },
    "warren_buffett": {
        "display_name": "沃伦·巴菲特 / Warren Buffett",
        "description": "奥马哈先知 / The Oracle of Omaha",
        "investing_style": "通过价值投资和长期持有，寻找基本面强劲且具有竞争优势的公司。 / Seeks companies with strong fundamentals and competitive advantages through value investing and long-term ownership.",
        "agent_func": warren_buffett_agent,
        "type": "analyst",
        "order": 10,
    },
    "technical_analyst": {
        "display_name": "技术分析师 / Technical Analyst",
        "description": "图表形态专家 / Chart Pattern Specialist",
        "investing_style": "专注于图表形态和市场趋势来做出投资决策，经常使用技术指标和价格行为分析。 / Focuses on chart patterns and market trends to make investment decisions, often using technical indicators and price action analysis.",
        "agent_func": technical_analyst_agent,
        "type": "analyst",
        "order": 11,
    },
    "fundamentals_analyst": {
        "display_name": "基本面分析师 / Fundamentals Analyst",
        "description": "财务报表专家 / Financial Statement Specialist",
        "investing_style": "深入研究财务报表和经济指标，通过基本面分析评估公司的内在价值。 / Delves into financial statements and economic indicators to assess the intrinsic value of companies through fundamental analysis.",
        "agent_func": fundamentals_analyst_agent,
        "type": "analyst",
        "order": 12,
    },
    "growth_analyst": {
        "display_name": "成长分析师 / Growth Analyst",
        "description": "增长专家 / Growth Specialist",
        "investing_style": "分析增长趋势和估值，通过增长分析识别增长机会。 / Analyzes growth trends and valuation to identify growth opportunities through growth analysis.",
        "agent_func": growth_analyst_agent,
        "type": "analyst",
        "order": 13,
    },
    "news_sentiment": {
        "display_name": "新闻情绪分析师 / News Sentiment Analyst",
        "description": "新闻情绪专家 / News Sentiment Specialist",
        "investing_style": "分析新闻情绪以预测市场走势，并通过新闻分析识别机会。 / Analyzes news sentiment to predict market movements and identify opportunities through news analysis.",
        "agent_func": news_sentiment_agent,
        "type": "analyst",
        "order": 14,
    },
    "sentiment_analyst": {
        "display_name": "情绪分析师 / Sentiment Analyst",
        "description": "市场情绪专家 / Market Sentiment Specialist",
        "investing_style": "评估市场情绪和投资者行为，通过行为分析预测市场走势并识别机会。 / Gauges market sentiment and investor behavior to predict market movements and identify opportunities through behavioral analysis.",
        "agent_func": sentiment_analyst_agent,
        "type": "analyst",
        "order": 15,
    },
    "valuation_analyst": {
        "display_name": "估值分析师 / Valuation Analyst",
        "description": "公司估值专家 / Company Valuation Specialist",
        "investing_style": "专门确定公司的公允价值，使用各种估值模型和财务指标进行投资决策。 / Specializes in determining the fair value of companies, using various valuation models and financial metrics for investment decisions.",
        "agent_func": valuation_analyst_agent,
        "type": "analyst",
        "order": 16,
    },
}

# Derive ANALYST_ORDER from ANALYST_CONFIG for backwards compatibility
ANALYST_ORDER = [(config["display_name"], key) for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])]


def get_analyst_nodes():
    """Get the mapping of analyst keys to their (node_name, agent_func) tuples."""
    return {key: (f"{key}_agent", config["agent_func"]) for key, config in ANALYST_CONFIG.items()}


def get_agents_list():
    """Get the list of agents for API responses."""
    return [
        {
            "key": key,
            "display_name": config["display_name"],
            "description": config["description"],
            "investing_style": config["investing_style"],
            "order": config["order"]
        }
        for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])
    ]

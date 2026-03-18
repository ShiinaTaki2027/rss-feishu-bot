"""
industry_news.py

聚合多个 RSS 源，用 Kimi 筛选关键人物动态和行业大事，推送到飞书。

环境变量：
    FEISHU_WEBHOOK   飞书机器人 Webhook
    KIMI_API_KEY     Kimi API Key（可选，配置后开启 AI 筛选）
"""

import os
import re
import time
import requests
import feedparser
from datetime import datetime, timezone, timedelta

# ===== Config =====
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
KIMI_API_KEY   = os.environ.get("KIMI_API_KEY", "")

# 只抓最近 N 小时内的文章，避免推送旧闻
HOURS_LOOKBACK = 26

# 关注的关键人物（用于 Kimi prompt 提示）
KEY_FIGURES = [
    "黄仁勋", "Jensen Huang",
    "Sam Altman", "Greg Brockman",
    "杨植麟", "张磊",
    "Demis Hassabis", "Sundar Pichai",
    "李飞飞", "朱啸虎",
    "Marc Andreessen", "Elon Musk",
    "Dario Amodei", "Yann LeCun",
]

# 关注的大会关键词
KEY_EVENTS = [
    "GTC", "Google I/O", "WWDC", "CES", "NeurIPS", "ICML", "ICLR",
    "世界人工智能大会", "乌镇峰会", "中关村论坛",
]

# RSS 源列表：(名称, URL, 语言)
RSS_FEEDS = [
    # 中文源
    ("36氪",         "https://36kr.com/feed",                          "zh"),
    ("机器之心",      "https://www.jiqizhixin.com/rss",                  "zh"),
    ("量子位",        "https://www.qbitai.com/feed",                     "zh"),
    # 英文源
    ("VentureBeat",  "https://venturebeat.com/feed/",                   "en"),
    ("TechCrunch",   "https://techcrunch.com/feed/",                    "en"),
    ("The Verge",    "https://www.theverge.com/rss/index.xml",          "en"),
]


# ===== RSS 抓取 =====

def fetch_recent_articles() -> list[dict]:
    """
    遍历所有 RSS 源，返回最近 HOURS_LOOKBACK 小时内的文章。
    每篇文章包含：title, url, source, summary, published
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    articles = []

    for source_name, feed_url, lang in RSS_FEEDS:
        try:
            print(f"抓取 {source_name}...")
            feed = feedparser.parse(feed_url)

            for entry in feed.entries:
                pub = _parse_published(entry)
                # 过滤太旧的文章
                if pub and pub < cutoff:
                    continue

                title   = entry.get("title", "").strip()
                url     = entry.get("link", "").strip()
                summary = _clean_html(entry.get("summary", ""))[:200]

                if not title or not url:
                    continue

                articles.append({
                    "title":     title,
                    "url":       url,
                    "source":    source_name,
                    "summary":   summary,
                    "published": pub.strftime("%m-%d %H:%M") if pub else "",
                    "lang":      lang,
                })

        except Exception as e:
            print(f"  {source_name} 抓取失败: {e}")
            continue

    print(f"共抓取到 {len(articles)} 篇近期文章")
    return articles


def _parse_published(entry) -> datetime | None:
    """从 feedparser entry 解析发布时间，统一转为 UTC aware datetime"""
    import time as time_module
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    try:
        ts = time_module.mktime(t)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _clean_html(text: str) -> str:
    """去除 HTML 标签，保留纯文本"""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ===== Kimi 筛选 =====

def kimi_filter_news(articles: list[dict]) -> str | None:
    """
    把近期文章送给 Kimi，筛选出关键人物动态和重要行业事件。
    """
    if not KIMI_API_KEY or not articles:
        return None

    # 整理成文本
    lines = []
    for i, a in enumerate(articles, 1):
        line = f"{i}. 【{a['source']}】{a['title']}"
        if a["summary"]:
            line += f"\n   摘要：{a['summary']}"
        if a["published"]:
            line += f"\n   时间：{a['published']}"
        line += f"\n   链接：{a['url']}"
        lines.append(line)

    articles_text = "\n\n".join(lines)

    key_figures_str = "、".join(KEY_FIGURES)
    key_events_str  = "、".join(KEY_EVENTS)

    prompt = f"""以下是今天从多个科技媒体抓取的 AI 行业资讯：

{articles_text}

请从中筛选出 **最多 6 条** 最值得关注的内容，优先选择：

1. 关键人物的公开讲话、采访、观点发布
   重点关注：{key_figures_str}
2. 重要行业大会或峰会的核心内容
   重点关注：{key_events_str}
3. 重大融资、并购、战略合作
4. 对行业格局影响深远的政策或监管动态

每条严格按以下格式输出：

**标题**（来源 · 时间）
一句话：说清楚发生了什么（不超过30字）
影响：为什么重要，对行业或用户意味着什么（不超过30字）
🔗 链接

条目之间空一行，不加序号，不加总结段落，不编造信息，直接输出。
如果没有符合条件的内容，输出：今日暂无重要人物动态或行业大事。
"""

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "moonshot-v1-8k",
                    "temperature": 0.4,
                    "max_tokens": 1200,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是一名专注 AI 行业的资深分析师，"
                                "擅长从海量资讯中找出真正影响行业走向的关键信息。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=60,
            )

            data = resp.json()
            if data.get("choices"):
                result = data["choices"][0]["message"]["content"]
                print("Kimi 筛选完成")
                return result.strip()

            error_type = data.get("error", {}).get("type", "")
            retryable  = error_type in {
                "engine_overloaded_error",
                "rate_limit_reached_error",
                "service_unavailable_error",
            }
            print(f"Kimi 调用失败（第 {attempt}/{max_retries} 次）:", data)
            if attempt == max_retries or not retryable:
                return None

        except requests.RequestException as e:
            print(f"Kimi 请求异常（第 {attempt}/{max_retries} 次）: {e}")
            if attempt == max_retries:
                return None

        delay = 2 * (2 ** (attempt - 1))
        print(f"{delay} 秒后重试...")
        time.sleep(delay)

    return None


def build_raw_card(articles: list[dict]) -> dict:
    """无 Kimi 时直接推送原始标题列表（取前 10）"""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    for a in articles[:10]:
        lines.append(f"• [{a['title']}]({a['url']})  _—{a['source']}_")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 行业动态 · {today}"},
                "template": "orange",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "\n".join(lines)},
                },
            ],
        },
    }


# ===== 飞书卡片 =====

def build_feishu_card(content: str) -> dict:
    today = datetime.now().strftime("%Y-%m-%d")
    sources = "、".join(s for s, _, _ in RSS_FEEDS)

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📡 行业动态 · {today}"},
                "template": "orange",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": content},
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"_来源：{sources}_\n_由 Kimi AI 从近 {HOURS_LOOKBACK}h 资讯中筛选_",
                    },
                },
            ],
        },
    }


# ===== 主流程 =====

def main():
    print("=" * 40)
    print("RSS 行业动态 → 飞书")
    print("=" * 40)

    # 1. 抓取近期文章
    articles = fetch_recent_articles()
    if not articles:
        print("未抓取到任何文章，退出")
        return

    # 2. Kimi 筛选
    if KIMI_API_KEY:
        print(f"正在让 Kimi 从 {len(articles)} 篇文章中筛选关键动态...")
        content = kimi_filter_news(articles)
    else:
        print("未配置 KIMI_API_KEY，跳过筛选")
        content = None

    # 3. 构建卡片
    card = build_feishu_card(content) if content else build_raw_card(articles)

    # 4. 推送
    if not FEISHU_WEBHOOK:
        import json
        print("未配置 FEISHU_WEBHOOK，打印卡片内容：")
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    print("飞书推送结果:", resp.json().get("msg", ""))


if __name__ == "__main__":
    main()

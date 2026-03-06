import requests
import re
import os
from datetime import datetime

# ===== Config =====
GITHUB_REPO = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")


def get_latest_issue():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "per_page": 1, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    issues = resp.json()
    return issues[0] if issues else None


def parse_markdown(body):
    sections = {}
    current_section = None

    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('## '):
            current_section = line[3:].strip()
            sections[current_section] = []
        elif line.startswith('###'):
            continue
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            text = line[2:].strip()
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
            text = re.sub(r'`[^`]+`', '', text).strip()
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            if text:
                sections[current_section].append(text)

    return sections


def build_feishu_card(issue, sections):
    today = datetime.now().strftime("%Y-%m-%d")
    elements = []

    EMOJI_MAP = {
        "要闻":           "🗞️ 要闻",
        "模型发布":        "🚀 模型发布",
        "开发生态":        "🛠️ 开发生态",
        "技术与洞察":      "🔬 技术与洞察",
        "行业动态":        "📊 行业动态",
        "前瞻与传闻":      "🔮 前瞻与传闻",
        "AI for Science": "🧪 AI for Science",
        "具身智能":        "🤖 具身智能",
        "AI音乐":         "🎵 AI音乐",
        "AI绘画":         "🎨 AI绘画",
        "AI视频":         "🎬 AI视频",
        "工具推荐":        "⚙️ 工具推荐",
        "概览":           "📋 概览",
        "产品动态":        "📱 产品动态",
    }

    overview_lines = []
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        overview_lines.append(f"**{display_title}**")
        for item in items:
            overview_lines.append(f"• {item}")
        overview_lines.append("")

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": "\n".join(overview_lines).strip()
        }
    })

    elements.append({"tag": "hr"})

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"[📖 查看完整原文 →]({issue['html_url']})"
        }
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🤖 AI 早报 · {today}"
                },
                "template": "blue"
            },
            "elements": elements
        }
    }


def main():
    if not FEISHU_WEBHOOK:
        print("FEISHU_WEBHOOK not set")
        return

    print("Fetching latest issue...")
    issue = get_latest_issue()
    if not issue:
        print("No issue found")
        return

    print(f"Got: {issue['title']}")
    sections = parse_markdown(issue['body'])
    print(f"Parsed {len(sections)} sections: {list(sections.keys())}")

    card = build_feishu_card(issue, sections)
    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    print("Result:", resp.json())


if __name__ == "__main__":
    main()

import requests
import re
import os
from datetime import datetime

# ===== Config =====
GITHUB_REPO = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")

EMOJI_MAP = {
    "要闻":            "🗞️ 要闻",
    "模型发布":         "🚀 模型发布",
    "开发生态":         "🛠️ 开发生态",
    "技术与洞察":       "🔬 技术与洞察",
    "行业动态":         "📊 行业动态",
    "前瞻与传闻":       "🔮 前瞻与传闻",
    "AI for Science":  "🧪 AI for Science",
    "具身智能":         "🤖 具身智能",
    "AI音乐":          "🎵 AI音乐",
    "AI绘画":          "🎨 AI绘画",
    "AI视频":          "🎬 AI视频",
    "工具推荐":         "⚙️ 工具推荐",
    "产品动态":         "📱 产品动态",
}


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


def extract_overview(body):
    sections = {}
    current_section = None
    in_overview = False

    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('## ') and line[3:].strip() == '概览':
            in_overview = True
            continue
        if in_overview and line.startswith('## '):
            break
        if not in_overview:
            continue
        if line.startswith('### '):
            current_section = line[4:].strip()
            sections[current_section] = []
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            raw = line[2:].strip()
            url = None
            for m in re.finditer(r'\(([^)]+)\)', raw):
                c = m.group(1)
                if c.startswith('http'):
                    url = c
                    break
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw)
            text = re.sub(r'`[^`]+`', '', text).strip()
            text = re.sub(r'\s*#\d+\s*$', '', text).strip()
            if text:
                sections[current_section].append({"text": text, "url": url})

    return sections


def build_feishu_card(issue, sections):
    today = datetime.now().strftime("%Y-%m-%d")
    elements = []

    overview_lines = []
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        overview_lines.append(f"**{display_title}**")
        for item in items:
            text = item["text"]
            url = item["url"]
            overview_lines.append(f"• {text} [↗]({url})" if url else f"• {text}")
        overview_lines.append("")

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": "\n".join(overview_lines).strip()}
    })
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": f"[📖 查看完整原文 →]({issue['html_url']})"}
    })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🤖 AI 早报 · {today}"},
                "template": "blue"
            },
            "elements": elements
        }
    }


def push_to_serverchan(issue, sections):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        lines.append(f"### {display_title}")
        for item in items:
            text = item["text"]
            url = item["url"]
            lines.append(f"- [{text}]({url})" if url else f"- {text}")
        lines.append("")
    lines.append(f"---\n[📖 查看完整原文]({issue['html_url']})")

    url = f"https://sctapi.ftqq.com/{SERVERCHAN_KEY}.send"
    resp = requests.post(url, data={
        "title": f"🤖 AI 早报 · {today}",
        "desp": "\n".join(lines).strip()
    }, timeout=10)
    print("Server酱推送结果:", resp.json())


def main():
    print("Fetching latest issue...")
    issue = get_latest_issue()
    if not issue:
        print("No issue found")
        return

    print(f"Got: {issue['title']}")
    sections = extract_overview(issue['body'])
    print(f"Parsed {len(sections)} sections: {list(sections.keys())}")

    if not sections:
        print("Warning: no overview sections found")
        return

    # 推送飞书
    if FEISHU_WEBHOOK:
        card = build_feishu_card(issue, sections)
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
        print("飞书推送结果:", resp.json())
    else:
        print("FEISHU_WEBHOOK not set, skipping")

    # 推送 Server酱（微信提醒）
    if SERVERCHAN_KEY:
        push_to_serverchan(issue, sections)
    else:
        print("SERVERCHAN_KEY not set, skipping")

    # 生成长图
    try:
        from generate_image import generate_image
        img_path = generate_image(issue, sections, "daily_report.png")
        print(f"长图已生成: {img_path}")
    except Exception as e:
        print(f"生图失败（不影响推送）: {e}")


if __name__ == "__main__":
    main()

import requests
import re
import os
from datetime import datetime

# ===== Config =====
GITHUB_REPO = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

# 分类 emoji 映射表（未匹配到的自动用 📌）
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
    """
    只提取 ## 概览 区域内的内容。
    概览区域结构：
      ## 概览
        ### 要闻          ← 三级标题作为分类
        - [条目文字](链接)
        ### 模型发布
        - ...
    遇到下一个 ## 二级标题时停止。
    """
    sections = {}
    current_section = None
    in_overview = False

    for line in body.split('\n'):
        line = line.strip()
        if not line:
            continue

        # 进入概览区域
        if line.startswith('## ') and line[3:].strip() == '概览':
            in_overview = True
            continue

        # 离开概览区域（遇到下一个 ## 标题）
        if in_overview and line.startswith('## '):
            break

        if not in_overview:
            continue

        # ### 三级标题 = 分类
        if line.startswith('### '):
            current_section = line[4:].strip()
            sections[current_section] = []

        # 列表条目
        elif (line.startswith('- ') or line.startswith('* ')) and current_section is not None:
            raw = line[2:].strip()

            # 提取第一个外部链接（排除 #数字 锚点）
            url = None
            for m in re.finditer(r'\(([^)]+)\)', raw):
                candidate = m.group(1)
                if candidate.startswith('http'):
                    url = candidate
                    break

            # 提取文字
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
            if url:
                overview_lines.append(f"• {text} [↗]({url})")
            else:
                overview_lines.append(f"• {text}")

        overview_lines.append("")  # 分类间空行

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
    sections = extract_overview(issue['body'])
    print(f"Parsed {len(sections)} sections: {list(sections.keys())}")

    if not sections:
        print("Warning: no overview sections found, check markdown structure")
        return

    card = build_feishu_card(issue, sections)
    resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    print("Result:", resp.json())


if __name__ == "__main__":
    main()

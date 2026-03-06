import requests
import re
import os
import base64
from datetime import datetime

# ===== Config =====
GITHUB_REPO    = "imjuya/juya-ai-daily"
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
IMGBB_KEY      = os.environ.get("IMGBB_KEY", "")

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


def upload_to_imgbb(image_path):
    """上传图片到 imgbb，返回公开 URL"""
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": IMGBB_KEY, "image": image_data},
        timeout=30
    )
    result = resp.json()
    if result.get("success"):
        url = result["data"]["url"]
        print(f"图片上传成功: {url}")
        return url
    else:
        print("图片上传失败:", result)
        return None


def push_image_to_feishu(image_url, issue_url):
    """通过 Webhook 发送图片消息到飞书群"""
    today = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🖼️ AI 早报长图 · {today}"},
                "template": "green"
            },
            "elements": [
                {
                    "tag": "img",
                    "img_key": image_url,   # imgbb URL 直接放这里
                    "alt": {"tag": "plain_text", "content": "AI 早报长图"},
                    "mode": "fit_horizontal"
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"[📖 查看完整原文 →]({issue_url})"
                    }
                }
            ]
        }
    }
    resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=10)
    result = resp.json()
    print("飞书图片推送结果:", result)

    # 飞书卡片 img_key 需要真正的 image_key，用 URL 会失败
    # 改用图片链接卡片方式
    if result.get("StatusCode") != 0:
        print("卡片发送失败，改用富文本图片方式...")
        fallback = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"🖼️ AI 早报长图 · {today}",
                        "content": [
                            [{"tag": "img", "image_key": image_url}],
                            [{"tag": "a", "text": "📖 查看完整原文", "href": issue_url}]
                        ]
                    }
                }
            }
        }
        resp2 = requests.post(FEISHU_WEBHOOK, json=fallback, timeout=10)
        print("飞书富文本图片推送结果:", resp2.json())


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

    # 1. 推送飞书文字卡片
    if FEISHU_WEBHOOK:
        card = build_feishu_card(issue, sections)
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
        print("飞书文字卡片推送结果:", resp.json())
    else:
        print("FEISHU_WEBHOOK not set, skipping")

    # 2. 推送 Server酱（微信提醒）
    if SERVERCHAN_KEY:
        push_to_serverchan(issue, sections)
    else:
        print("SERVERCHAN_KEY not set, skipping")

    # 3. 生成长图 → 上传图床 → 推送飞书图片
    if IMGBB_KEY and FEISHU_WEBHOOK:
        try:
            from generate_image import generate_image
            img_path = generate_image(issue, sections, "daily_report.png")
            image_url = upload_to_imgbb(img_path)
            if image_url:
                push_image_to_feishu(image_url, issue['html_url'])
        except Exception as e:
            print(f"生图/推图失败: {e}")
    else:
        print("IMGBB_KEY or FEISHU_WEBHOOK not set, skipping image push")


if __name__ == "__main__":
    main()

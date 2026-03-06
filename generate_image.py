"""
generate_image.py
把 AI 早报内容渲染成长图，保存为 daily_report.png
依赖：pip install requests Pillow
"""

import requests
import re
import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import textwrap

# ===== Config =====
GITHUB_REPO = "imjuya/juya-ai-daily"

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

# ===== 颜色主题 =====
BG_COLOR       = (18, 18, 24)       # 深色背景
HEADER_COLOR   = (30, 58, 95)       # 标题栏深蓝
TITLE_COLOR    = (255, 255, 255)    # 主标题白色
SECTION_COLOR  = (99, 179, 237)     # 分类标题蓝色
ITEM_COLOR     = (220, 220, 220)    # 条目文字浅灰
URL_COLOR      = (99, 179, 237)     # 链接颜色
DIM_COLOR      = (120, 120, 140)    # 辅助文字
DIVIDER_COLOR  = (50, 50, 65)       # 分割线
ACCENT_COLOR   = (66, 153, 225)     # 强调色

# ===== 布局 =====
WIDTH          = 800
PADDING        = 48
HEADER_H       = 80
LINE_HEIGHT    = 36
SECTION_GAP    = 20
ITEM_INDENT    = 20


def get_latest_issue():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    params = {"state": "open", "per_page": 1, "sort": "created", "direction": "desc"}
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    return resp.json()[0] if resp.json() else None


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


def load_font(size, bold=False):
    """加载系统中文字体"""
    font_paths = [
        # Linux (GitHub Actions)
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def measure_text_height(text, font, max_width):
    """计算多行文字的总高度"""
    dummy = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(dummy)
    lines = []
    for paragraph in text.split('\n'):
        wrapped = textwrap.wrap(paragraph, width=int(max_width / (font.size * 0.6 + 1)) + 2)
        lines.extend(wrapped if wrapped else [''])
    return len(lines) * LINE_HEIGHT


def draw_text_wrapped(draw, text, x, y, font, color, max_width):
    """绘制自动换行文字，返回绘制后的 y 坐标"""
    for paragraph in text.split('\n'):
        wrapped = textwrap.wrap(paragraph, width=int(max_width / (font.size * 0.55 + 1)) + 2)
        if not wrapped:
            y += LINE_HEIGHT
            continue
        for line in wrapped:
            draw.text((x, y), line, font=font, fill=color)
            y += LINE_HEIGHT
    return y


def calculate_total_height(sections, font_section, font_item):
    """预计算总高度"""
    h = HEADER_H + PADDING * 2  # header + top/bottom padding
    content_width = WIDTH - PADDING * 2 - ITEM_INDENT

    for title, items in sections.items():
        h += LINE_HEIGHT + SECTION_GAP  # 分类标题
        for item in items:
            text = f"• {item['text']}"
            h += measure_text_height(text, font_item, content_width)
        h += SECTION_GAP  # 分类底部间距

    h += LINE_HEIGHT + PADDING  # 底部来源行
    return h


def generate_image(issue, sections, output_path="daily_report.png"):
    today = datetime.now().strftime("%Y-%m-%d")

    font_title   = load_font(26, bold=True)
    font_section = load_font(20, bold=True)
    font_item    = load_font(17)
    font_url     = load_font(14)
    font_footer  = load_font(14)

    total_height = calculate_total_height(sections, font_section, font_item)
    img = Image.new('RGB', (WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # ===== Header =====
    draw.rectangle([0, 0, WIDTH, HEADER_H], fill=HEADER_COLOR)
    draw.text((PADDING, (HEADER_H - 30) // 2), f"🤖  AI 早报 · {today}",
              font=font_title, fill=TITLE_COLOR)

    y = HEADER_H + PADDING

    # ===== 分类内容 =====
    for title, items in sections.items():
        if not items:
            continue

        display_title = EMOJI_MAP.get(title, f"📌 {title}")

        # 分类标题背景条
        draw.rectangle([PADDING - 8, y - 4, WIDTH - PADDING + 8, y + LINE_HEIGHT],
                       fill=(30, 40, 60))
        draw.text((PADDING, y), display_title, font=font_section, fill=SECTION_COLOR)
        y += LINE_HEIGHT + 8

        # 条目
        for item in items:
            text = f"• {item['text']}"
            y = draw_text_wrapped(draw, text,
                                  PADDING + ITEM_INDENT, y,
                                  font_item, ITEM_COLOR,
                                  WIDTH - PADDING * 2 - ITEM_INDENT)
            # 链接提示
            if item['url']:
                short_url = item['url'][:55] + '...' if len(item['url']) > 55 else item['url']
                draw.text((PADDING + ITEM_INDENT + 12, y - 2),
                          f"↗ {short_url}", font=font_url, fill=URL_COLOR)
                y += LINE_HEIGHT - 8

        # 分类底部分割线
        y += SECTION_GAP // 2
        draw.line([(PADDING, y), (WIDTH - PADDING, y)], fill=DIVIDER_COLOR, width=1)
        y += SECTION_GAP // 2

    # ===== 底部来源 =====
    y += 8
    draw.text((PADDING, y),
              f"来源：github.com/{GITHUB_REPO}  |  {issue['html_url']}",
              font=font_footer, fill=DIM_COLOR)

    img.save(output_path, 'PNG', quality=95)
    print(f"图片已生成：{output_path}  ({WIDTH}x{total_height})")
    return output_path


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

    generate_image(issue, sections, "daily_report.png")


if __name__ == "__main__":
    main()

"""Compact Chinese image menus for the API plugin."""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LABELS = {"text": "文字", "image": "图片", "video": "视频", "audio": "语音"}
COLORS = {"text": "#197E79", "image": "#C98537", "video": "#7B60A7", "audio": "#C25E76"}
FONT_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
)


def _font(size):
    for path in FONT_PATHS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_menu(entries, category=""):
    """Render current, accessible API names; category is one of text/image/video/audio."""
    grouped = {kind: sorted((entry.name + ("（暂不可用）" if not entry.valid else "")
                            for entry in entries if entry.type == kind)) for kind in LABELS}
    if category:
        names = grouped[category]
        rows = max(1, (len(names) + 1) // 2)
        height = max(600, 340 + rows * 64 + 120)
    else:
        height = 1020
    image = Image.new("RGB", (1200, height), "#F4F6F3")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 38, 1158, 210), radius=32, fill="#19343A")
    title = "娱乐 API · " + LABELS[category] if category else "娱乐 API · 菜单"
    draw.text((80, 70), title, font=_font(55), fill="white")
    draw.text((80, 151), "群聊先 @机器人；私聊直接发送命令或关键词", font=_font(26), fill="#D7EAE7")
    if category:
        draw.text((60, 245), f"收录 {len(grouped[category])} 项 · 已标注失效接口", font=_font(31), fill="#3A5459")
        for idx, name in enumerate(grouped[category]):
            x = 60 + (idx % 2) * 550
            y = 305 + (idx // 2) * 64
            draw.rounded_rectangle((x, y, x + 520, y + 50), radius=12, fill="white")
            draw.rectangle((x, y + 7, x + 6, y + 43), fill=COLORS[category])
            draw.text((x + 25, y + 8), name, font=_font(28), fill="#19343A")
        footer = "/娱乐 返回总菜单 · 部分接口需要额外参数或可能临时不可用"
    else:
        draw.text((60, 244), "选择分类查看完整列表", font=_font(34), fill="#3A5459")
        for idx, (kind, label) in enumerate(LABELS.items()):
            x = 60 + (idx % 2) * 550
            y = 315 + (idx // 2) * 265
            draw.rounded_rectangle((x, y, x + 520, y + 235), radius=25, fill="white")
            draw.rectangle((x + 24, y + 28, x + 34, y + 88), fill=COLORS[kind])
            draw.text((x + 53, y + 25), f"{label}  ·  {len(grouped[kind])} 项", font=_font(37), fill="#19343A")
            draw.text((x + 27, y + 104), f"/娱乐 {label}", font=_font(27), fill=COLORS[kind])
            examples = "  ·  ".join(grouped[kind][:3]) or "当前无可用项目"
            draw.text((x + 27, y + 166), examples, font=_font(24), fill="#52696F")
        footer = "资讯与热榜：/资讯   ·   分类：/娱乐 图片   ·   参数：/查看api 项目名"
    draw.text((60, height - 78), footer, font=_font(24), fill="#52696F")
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()

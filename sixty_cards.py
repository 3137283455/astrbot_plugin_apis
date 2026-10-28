"""Readable 60s results and a separate catalog, without growing the old help poster."""
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw

from .entertainment_menu import _font


def _png(image):
    out = BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def wrap(draw, text, font, width):
    lines, current = [], ""
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
        elif current and draw.textlength(current + char, font=font) > width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def render_card(title, text):
    font = _font(32)
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    lines = wrap(draw, text, font, 980)
    clipped = len(lines) > 100
    lines = lines[:100]
    if clipped:
        lines += ["", "内容较长，以上展示前 100 行。"]
    height = max(520, 370 + len(lines) * 48)
    image = Image.new("RGB", (1120, height), "#F1F3F8")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 28, 1092, height - 28), radius=30, fill="white")
    draw.rounded_rectangle((28, 28, 1092, 190), radius=30, fill="#172B4D")
    draw.rectangle((28, 150, 1092, 190), fill="#172B4D")
    draw.text((65, 48), "60s  /  慧慧资讯站", font=_font(23), fill="#8ADAC8")
    draw.text((65, 95), title, font=_font(48), fill="white")
    y = 225
    for line in lines:
        draw.text((65, y), line, font=font, fill="#22354D")
        y += 48
    draw.line((65, height - 98, 1055, height - 98), fill="#DDE3ED", width=2)
    draw.text((65, height - 80), "60s API · 获取于 " + datetime.now().strftime("%Y-%m-%d %H:%M"), font=_font(22), fill="#687891")
    return _png(image)


def render_catalog(rows, category=""):
    grouped = {cat: [r for r in rows if r["category"] == cat] for cat in ("热榜", "资讯", "工具", "图片", "趣味")}
    height = 340 + sum(88 + ((len(v) + 2) // 3) * 100 for v in grouped.values() if v) + 160
    image = Image.new("RGB", (1200, height), "#F1F3F8")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 30, 1170, 240), radius=30, fill="#172B4D")
    draw.text((65, 60), "60s · 资讯与工具" + (" / " + category if category else ""), font=_font(48), fill="white")
    draw.text((65, 142), "群聊先 @机器人，私聊直接用；也可以让慧慧帮你查", font=_font(27), fill="#CFDFED")
    draw.text((65, 192), "/资讯 热榜  /资讯 工具  /资讯 趣味  可分类查看", font=_font(26), fill="#8ADAC8")
    y = 278
    for cat, items in grouped.items():
        if not items:
            continue
        draw.text((50, y), f"{cat}  /  {len(items)} 项", font=_font(35), fill="#172B4D")
        y += 70
        for i, row in enumerate(items):
            x = 45 + i % 3 * 375
            top = y + i // 3 * 100
            draw.rounded_rectangle((x, top, x + 360, top + 86), radius=14, fill="white")
            draw.text((x + 14, top + 9), "/" + row["name"], font=_font(27), fill="#172B4D")
            hint = ("例：" + row["example"].split(" ", 1)[-1]) if row["params"] else "直接发送即可"
            draw.text((x + 14, top + 48), hint, font=_font(20), fill="#687891")
        y += ((len(items) + 2) // 3) * 100 + 18
    draw.text((50, height - 135), "例：/天气 上海  ·  /翻译 hello world  ·  /发病 慧慧", font=_font(27), fill="#172B4D")
    draw.text((50, height - 85), "参数统一放命令后；仅展示本机已接入的功能，数据以源站为准", font=_font(24), fill="#687891")
    return _png(image)

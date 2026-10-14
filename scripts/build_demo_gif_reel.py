# -*- coding: utf-8 -*-
"""离线生成 docs/demo.gif：麦麦复活赛「怀旧单品博物馆」产品轮播动图。
优先展示新增/替换图（珍宝三角、香菜冰旋风等），并混排其他有图单品，
直接反映站点当前的新图片。960x540，循环。"""
import os, json, glob
from PIL import Image, ImageDraw, ImageFont

BASE = r"D:/WorkbuddyTemp/2026-10-10-21-21-06/McMuseum"
PROD = os.path.join(BASE, "data", "nostalgic_products.json")
PDIR = os.path.join(BASE, "web", "assets", "products")
OUT = os.path.join(BASE, "docs", "demo.gif")
FONT = "C:/Windows/Fonts/simhei.ttf"

RED = (218, 41, 28)
YEL = (255, 199, 44)
DARK = (30, 27, 24)
GRAY = (138, 127, 114)
CREAM = (255, 246, 229)

# 优先展示：新增/替换图 + 代表性有图单品
PRIORITY = [
    "treasure_triangle", "cilantro_mcfloat", "crayfish_burger", "twisted_fries",
    "mc_rice_wrap", "matcha_mcfloat", "singapore_honey_mustard", "roujiamo",
    "dapanji_spicy_burger", "wax_cabbage_burger", "grape_yogurt_oat_mcfloat",
    "garlic_chili_sauce", "sakura_mcfloat", "durian_flavor",
]

def font(sz):
    return ImageFont.truetype(FONT, sz)

def wrap(text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        if fnt.getlength(cur + ch) > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines

def frame_product(p):
    im = Image.new("RGB", (960, 540), CREAM)
    d = ImageDraw.Draw(im)
    # 左侧产品图卡片
    card = Image.new("RGB", (520, 470), (255, 255, 255))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([0, 0, 519, 469], radius=24, fill=(255, 255, 255), outline=(234, 223, 208), width=2)
    imgp = os.path.join(PDIR, os.path.basename(p["image"]))
    try:
        pic = Image.open(imgp).convert("RGBA")
        pic.thumbnail((460, 410), Image.LANCZOS)
        card.paste(pic, ((520 - pic.width) // 2, (470 - pic.height) // 2), pic)
    except Exception:
        cd.text((40, 220), "（图暂无）", font=font(22), fill=GRAY)
    im.paste(card, (40, 35))
    # 右侧文字
    name_lines = wrap(p["name"], font(46), 320)
    y = 70
    for ln in name_lines[:2]:
        d.text((600, y), ln, font=font(46), fill=DARK)
        y += 56
    tag = f"{p.get('era','')} · {p.get('category','')}"
    d.text((602, y + 14), tag, font=font(22), fill=RED)
    d.text((602, 470), "麦麦复活赛 · 97 款怀旧单品博物馆", font=font(20), fill=GRAY)
    return im

def frame_title():
    im = Image.new("RGB", (960, 540), RED)
    d = ImageDraw.Draw(im)
    d.text((480, 150), "麦麦复活赛", font=font(72), fill=(255, 255, 255), anchor="mm")
    d.text((480, 240), "麦当劳怀旧单品博物馆 · 97 款", font=font(30), fill=YEL, anchor="mm")
    d.text((480, 320), "那些年下架的老朋友，由你投票决定谁返场", font=font(24), fill=(255, 255, 255), anchor="mm")
    d.text((480, 410), "🗳️ 真实麦当劳会员身份投票 · 🔒 只读不扣减", font=font(22), fill=(255, 230, 200), anchor="mm")
    return im

def frame_end():
    im = Image.new("RGB", (960, 540), DARK)
    d = ImageDraw.Draw(im)
    d.text((480, 200), "🚀 立即免费体验", font=font(54), fill=YEL, anchor="mm")
    d.text((480, 290), "mcmuseum-revival.app.workbuddy.host", font=font(28), fill=(255, 255, 255), anchor="mm")
    d.text((480, 370), "GitHub 搜 McMuseum · 点个 Star 支持作者", font=font(22), fill=(216, 210, 201), anchor="mm")
    return im

# 选品：优先 PRIORITY 中已有图者，再补足到 12 款
data = json.load(open(PROD, encoding="utf-8"))
prods = {p["id"]: p for p in data["products"]}
chosen = []
for pid in PRIORITY:
    p = prods.get(pid)
    if p and p.get("image") and os.path.exists(os.path.join(PDIR, os.path.basename(p["image"]))):
        chosen.append(p)
if len(chosen) < 12:
    for p in data["products"]:
        if len(chosen) >= 12:
            break
        if p not in chosen and p.get("image") and os.path.exists(os.path.join(PDIR, os.path.basename(p["image"]))):
            chosen.append(p)

frames = [frame_title()] + [frame_product(p) for p in chosen] + [frame_end()]
for i, f in enumerate(frames):
    f.save  # keep ref
# 时长：标题/结尾 900ms，产品帧 750ms
durs = [900] + [750] * len(chosen) + [1100]
frames[0].save(
    OUT, save_all=True, append_images=frames[1:],
    duration=durs, loop=0, optimize=True, disposal=2,
)
print(f"saved {OUT} ({os.path.getsize(OUT)//1024}KB), {len(frames)} frames, "
      f"loop {sum(durs)/1000:.1f}s; 展示单品: {[p['name'] for p in chosen]}")

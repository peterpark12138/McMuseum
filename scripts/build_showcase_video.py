# -*- coding: utf-8 -*-
"""
build_showcase_video.py — 生成 28 秒功能展示短视频 docs/showcase.mp4
结构（符合需求：开头 3 秒抓眼球 / 功能演示带文字 / 产品照片墙 AE 动效感 /
提及全部代码由 WorkBuddy 开发 / GitHub 投稿反馈 CTA / ≤30s / 字大）：

  S1 0.0–3.0s  钩子：深夜红底 + 3 款怀旧单品飞入 + 「还记得这些吗？」
  S2 3.0–8.0s  97 款怀旧单品博物馆：照片墙交错滑入
  S3 8.0–13.5s 真实麦当劳会员投票：站点截图 + 要点
  S4 13.5–19.0s GitHub Issue 官方计票：站点截图 + 要点
  S5 19.0–24.0s 产品照片墙：逐张弹入（AE 动效感）
  S6 24.0–28.0s CTA：WorkBuddy 开发 + GitHub 联系作者

纯离线合成：Pillow 逐帧绘制 → ffmpeg(rawvideo 管道) H.264 编码。
用法：python scripts/build_showcase_video.py
"""
import os
import math
import json
import subprocess
import sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1280, 720
FPS = 24
DUR = 28.0
TOTAL = int(DUR * FPS)  # 672
OUT = os.path.join(ROOT, "docs", "showcase.mp4")
ASSETS = os.path.join(ROOT, ".video_assets")

# ---- 颜色（麦当劳视觉）----
RED = (218, 41, 28)
RED_DARK = (140, 20, 12)
YELLOW = (255, 199, 44)
CREAM = (255, 248, 227)
DARK = (41, 32, 24)
WHITE = (255, 255, 255)

def _font(candidates, size):
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

F_HOOK = _font(["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"], 108)
F_TITLE = _font(["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"], 66)
F_MID = _font(["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"], 46)
F_BODY = _font(["C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/simhei.ttf"], 34)
F_SMALL = _font(["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"], 26)
F_URL = _font(["C:/Windows/Fonts/consolab.ttf", "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arialbd.ttf"], 34)

# ---- 动效工具 ----
def clamp01(x):
    return max(0.0, min(1.0, x))

def seg(t, a, b):
    return clamp01((t - a) / max(1e-6, (b - a)))

def ease_out_cubic(t):
    t = clamp01(t)
    return 1 - (1 - t) ** 3

def ease_out_back(t, s=1.70158):
    t = clamp01(t)
    t -= 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2

def lerp(a, b, k):
    return a + (b - a) * k

def text_layer(text, font, fill, stroke=(0, 0, 0), stroke_w=0):
    """渲染一行文字到独立 RGBA 图层，便于做缩放/位移动效。"""
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    box = d.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    w, h = box[2] - box[0] + 8, box[3] - box[1] + 8
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((4 - box[0], 4 - box[1]), text, font=font,
                               fill=fill, stroke_width=stroke_w, stroke_fill=stroke)
    return layer

def paste_alpha(base, layer, cx, cy, scale=1.0, alpha=1.0, angle=0.0):
    if scale != 1.0:
        w, h = layer.size
        layer = layer.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
    if angle:
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
    if alpha < 1.0:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    base.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))

def glow_bg(color, glow_rgba, glow_r=380, center=(W // 2, H // 2)):
    img = Image.new("RGBA", (W, H), color + (255,))
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(gl).ellipse(
        [center[0] - glow_r, center[1] - glow_r * 0.7, center[0] + glow_r, center[1] + glow_r * 0.7],
        fill=glow_rgba)
    gl = gl.filter(ImageFilter.GaussianBlur(120))
    img.alpha_composite(gl)
    return img

def rounded_shadow_card(img_inner, pad=0, radius=28, shadow_blur=18, shadow_alpha=110, off=(0, 10)):
    """把内容图包进白底圆角卡 + 投影，返回 RGBA。"""
    w, h = img_inner.size
    card = Image.new("RGBA", (w + pad * 2 + 40, h + pad * 2 + 40), (0, 0, 0, 0))
    sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(
        [20 + off[0], 20 + off[1], 20 + w + pad * 2 + off[0], 20 + h + pad * 2 + off[1]],
        radius=radius, fill=(0, 0, 0, shadow_alpha))
    card.alpha_composite(sh.filter(ImageFilter.GaussianBlur(shadow_blur)))
    body = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(body).rounded_rectangle([0, 0, body.width - 1, body.height - 1],
                                           radius=radius, fill=WHITE + (255,))
    if img_inner.mode != "RGBA":
        img_inner = img_inner.convert("RGBA")
    body.alpha_composite(img_inner, (pad, pad))
    card.alpha_composite(body, (20, 20))
    return card

def fit_cover(img, box_w, box_h):
    w, h = img.size
    k = max(box_w / w, box_h / h)
    img = img.resize((int(w * k), int(h * k)), Image.LANCZOS)
    l = (img.width - box_w) // 2
    t = (img.height - box_h) // 2
    return img.crop((l, t, l + box_w, t + box_h))

def fit_contain(img, box_w, box_h):
    w, h = img.size
    k = min(box_w / w, box_h / h)
    return img.resize((int(w * k), int(h * k)), Image.LANCZOS)

# ---- 素材 ----
# 产品图只使用用户提供的 docs/替换产品图/（该目录不入库，见 .gitignore）；
# 本脚本生成的 docs/showcase.mp4 为最终产物，可直接提交。
PROD_DIR = os.path.join(ROOT, "docs", "替换产品图")

HOOK_NAMES = ["扭扭薯条", "樱花麦旋风", "珍宝三角"]
WALL_NAMES = ["珍宝三角", "香菜冰旋风", "扭扭薯条", "神鲜虾虾堡",
              "抹茶麦旋风", "樱花麦旋风", "肉夹馍", "摇摇薯条",
              "蜂蜜芥末酱", "大盘鸡辣堡", "腊味菜菜堡", "葡萄燕麦麦旋风",
              "蒜蓉辣椒酱", "麦趣饭", "五色嫩鸡麦饭卷",
              "五色至牛麦饭卷", "香芋派", "榴莲麦旋风"]

def load_prod(name):
    p = os.path.join(PROD_DIR, name + ".png")
    if os.path.exists(p):
        return Image.open(p).convert("RGBA")
    return None

def prod_card(pid, box=200):
    im = load_prod(pid)
    if im is None:
        card = Image.new("RGBA", (box, box), WHITE + (255,))
        ImageDraw.Draw(card).text((box // 2, box // 2), "?", font=F_MID, fill=(160, 150, 140), anchor="mm")
        return card
    inner = fit_contain(im, box - 28, box - 28)
    card = Image.new("RGBA", (box, box), WHITE + (255,))
    card.alpha_composite(inner, ((box - inner.width) // 2, (box - inner.height) // 2))
    return rounded_shadow_card(card, pad=0, radius=22, shadow_alpha=70, off=(0, 6))

def shot_card(name, box_w, box_h):
    p = os.path.join(ASSETS, name)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert("RGBA")
    inner = fit_cover(im, box_w, box_h)
    return rounded_shadow_card(inner, pad=0, radius=24, shadow_alpha=130, off=(0, 14))

BOUNDARIES = [3.0, 8.0, 13.5, 19.0, 24.0]

def white_flash(img, t):
    """段落切换的白色闪光（AE 感的硬切衔接）。"""
    for b in BOUNDARIES:
        k = seg(t, b - 0.10, b + 0.04)
        if 0 < k < 1:
            a = int(200 * (1 - k))
            img.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, a)))
    return img

def watermark(img):
    layer = text_layer("McMuseum · 麦麦复活赛", F_SMALL, (255, 255, 255, 150))
    paste_alpha(img, layer, W - 20 - layer.width // 2, H - 26)
    return img

# ---- S1 钩子 0–3s ----
def s1(img, t):
    k_bg = seg(t, 0.0, 0.35)
    base = glow_bg(tuple(int(lerp(20, c, k_bg)) for c in RED_DARK), (255, 120, 60, 60))
    img.alpha_composite(base)
    # 三款单品从两侧飞入
    slots = [(W * 0.28, H * 0.42, -7), (W * 0.5, H * 0.36, 4), (W * 0.72, H * 0.44, 8)]
    for i, pid in enumerate(HOOK_NAMES):
        st = 0.25 + i * 0.22
        k = ease_out_back(seg(t, st, st + 0.55))
        card = prod_card(pid, 210)
        x0, y0 = slots[i][0], -140
        x = lerp(x0, slots[i][0], k)
        y = lerp(y0, slots[i][1], k)
        paste_alpha(img, card, x, y, scale=0.6 + 0.4 * k, alpha=k, angle=slots[i][2])
    # 主标题 scale-punch
    k1 = ease_out_back(seg(t, 0.9, 1.45))
    layer = text_layer("还记得这些吗？", F_HOOK, YELLOW + (255,), stroke=(60, 12, 6), stroke_w=6)
    if k1 > 0:
        paste_alpha(img, layer, W / 2, H * 0.72, scale=0.5 + 0.5 * k1, alpha=min(1, k1 * 1.5))
    # 副标题
    k2 = ease_out_cubic(seg(t, 1.8, 2.4))
    layer2 = text_layer("那些年，从菜单上消失的老味道", F_MID, WHITE + (255,), stroke=(0, 0, 0), stroke_w=3)
    paste_alpha(img, layer2, W / 2, lerp(H + 60, H * 0.90, k2), alpha=k2)

# ---- S2 博物馆 3–8s ----
def s2(img, t):
    img.alpha_composite(Image.new("RGBA", (W, H), CREAM + (255,)))
    k_t = ease_out_back(seg(t, 3.1, 3.7))
    title = text_layer("97 款怀旧单品博物馆", F_TITLE, RED + (255,), stroke=(255, 255, 255), stroke_w=2)
    paste_alpha(img, title, W / 2, lerp(-70, 96, k_t), alpha=min(1, k_t * 1.6))
    sub = text_layer("每款都带年份 · 故事 · 证据等级", F_BODY, (120, 96, 60))
    k_s = ease_out_cubic(seg(t, 3.5, 4.1))
    paste_alpha(img, sub, W / 2, lerp(40, 168, k_s), alpha=k_s)
    # 6×3 照片墙交错滑入（行高压缩到画幅内）
    cols, cell, gap = 6, 150, 16
    pitch = cell + gap
    gw = cols * cell + (cols - 1) * gap
    x0 = (W - gw) // 2 + cell // 2
    row_tops = 285, 451, 617  # 三行中心，底部 692 < 720
    for i, pid in enumerate(WALL_NAMES):
        r, c = divmod(i, cols)
        st = 3.6 + i * 0.09
        k = ease_out_back(seg(t, st, st + 0.5))
        if k <= 0:
            continue
        card = prod_card(pid, cell)
        from_left = (r % 2 == 0)
        xs = -200 if from_left else W + 200
        x = lerp(xs, x0 + c * pitch, k)
        y = row_tops[r]
        paste_alpha(img, card, x, y, scale=0.7 + 0.3 * k, alpha=k)

# ---- S3 真实投票 8–13.5s ----
def s3(img, t):
    img.alpha_composite(glow_bg(RED, (255, 210, 120, 45)))
    k_t = ease_out_back(seg(t, 8.1, 8.7))
    title = text_layer("用你的真实麦当劳会员身份投票", F_TITLE, WHITE + (255,), stroke=(90, 15, 8), stroke_w=4)
    paste_alpha(img, title, W / 2, lerp(-60, 92, k_t), alpha=min(1, k_t * 1.6))
    for i, (txt, st) in enumerate([("1 张基础票 + 每 100 积分 1 张积分票", 8.9),
                                   ("全程只读 MCP · 绝不扣积分 · 一人一品一票", 9.4)]):
        k = ease_out_cubic(seg(t, st, st + 0.5))
        layer = text_layer(txt, F_BODY, YELLOW + (255,), stroke=(0, 0, 0), stroke_w=2)
        paste_alpha(img, layer, W / 2, lerp(30, 168 + i * 56, k), alpha=k)
    card = shot_card("shot_rank.png", 760, 430)
    if card is not None:
        k = ease_out_back(seg(t, 9.9, 10.9))
        y = lerp(H + 260, H * 0.66, k)
        paste_alpha(img, card, W / 2, y, scale=0.85 + 0.15 * k, alpha=k, angle=-3.5)

# ---- S4 GitHub 计票 13.5–19s ----
def s4(img, t):
    img.alpha_composite(glow_bg(DARK, (255, 199, 44, 40)))
    k_t = ease_out_back(seg(t, 13.6, 14.2))
    title = text_layer("GitHub Issue 官方计票", F_TITLE, YELLOW + (255,), stroke=(0, 0, 0), stroke_w=4)
    paste_alpha(img, title, W * 0.30, lerp(-60, 110, k_t), alpha=min(1, k_t * 1.6))
    lines = [("匿名票数回流 Issue", 14.3), ("只认信任锚点账号", 14.8), ("透明可核 · 不可伪造", 15.3)]
    for i, (txt, st) in enumerate(lines):
        k = ease_out_cubic(seg(t, st, st + 0.45))
        layer = text_layer(txt, F_MID, WHITE + (255,), stroke=(0, 0, 0), stroke_w=2)
        paste_alpha(img, layer, W * 0.28, lerp(30, 208 + i * 70, k), alpha=k)
    card = shot_card("shot_home.png", 640, 370)
    if card is not None:
        k = ease_out_back(seg(t, 15.6, 16.8))
        x = lerp(W + 380, W - 20 - card.width // 2, k)
        paste_alpha(img, card, x, H * 0.58, scale=0.9 + 0.1 * k, alpha=k, angle=4)

# ---- S5 照片墙 19–24s（AE 动效感：逐张弹入）----
def s5(img, t):
    img.alpha_composite(Image.new("RGBA", (W, H), YELLOW + (255,)))
    k_t = ease_out_back(seg(t, 19.1, 19.7))
    title = text_layer("他们值得一次复活赛", F_TITLE, RED + (255,), stroke=(255, 255, 255), stroke_w=3)
    paste_alpha(img, title, W / 2, lerp(-60, 84, k_t), alpha=min(1, k_t * 1.6))
    cols, cell, gap = 6, 150, 16
    pitch = cell + gap
    gw = cols * cell + (cols - 1) * gap
    x0 = (W - gw) // 2 + cell // 2
    row_tops = 275, 441, 607  # 三行中心，底部 682 < 720
    ids = WALL_NAMES[9:] + WALL_NAMES[:9]  # 换个顺序，与 S2 照片墙错开观感
    for i, pid in enumerate(ids[:18]):
        r, c = divmod(i, cols)
        st = 19.3 + i * 0.13
        k = ease_out_back(seg(t, st, st + 0.42))
        if k <= 0:
            continue
        card = prod_card(pid, cell)
        x, y = x0 + c * pitch, row_tops[r]
        paste_alpha(img, card, x, y, scale=k, alpha=clamp01(k * 1.4))

# ---- S6 CTA 24–28s ----
def s6(img, t):
    img.alpha_composite(glow_bg(RED, (255, 220, 150, 55)))
    rows = [
        ("全部代码由 WorkBuddy 开发", F_TITLE, YELLOW + (255,), (90, 15, 8), 5, 24.2, 208),
        ("投稿你心中的怀旧单品 · 意见反馈", F_MID, WHITE + (255,), (0, 0, 0), 3, 25.2, 330),
        ("GitHub 联系作者 · 投 star 支持我们", F_MID, WHITE + (255,), (0, 0, 0), 3, 26.0, 424),
    ]
    for txt, font, fill, stroke, sw, st, y in rows:
        k = ease_out_back(seg(t, st, st + 0.55))
        layer = text_layer(txt, font, fill, stroke=stroke, stroke_w=sw)
        paste_alpha(img, layer, W / 2, lerp(y + 60, y, ease_out_cubic(seg(t, st, st + 0.55))),
                    scale=0.6 + 0.4 * k, alpha=min(1, k * 1.5))
    k_url = ease_out_cubic(seg(t, 26.6, 27.2))
    url = text_layer("github.com/peterpark12138/McMuseum", F_URL, DARK + (255,))
    paste_alpha(img, rounded_shadow_card(url, pad=14, radius=14, shadow_alpha=90), W / 2,
                lerp(H + 50, 545, k_url), alpha=k_url)

SEG_FUNCS = [(0.0, s1), (3.0, s2), (8.0, s3), (13.5, s4), (19.0, s5), (24.0, s6)]

def render(t):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    for start, fn in reversed(SEG_FUNCS):
        if t >= start:
            fn(img, t)
            break
    white_flash(img, t)
    watermark(img)
    return img

def main():
    ff = None
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ff = "ffmpeg"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cmd = [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", OUT]
    print("ffmpeg:", ff)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(TOTAL):
        t = i / FPS
        frame = render(t).convert("RGB")
        proc.stdin.write(frame.tobytes())
        if i % 48 == 0:
            print(f"frame {i}/{TOTAL} (t={t:.1f}s)", flush=True)
    proc.stdin.close()
    proc.wait()
    size = os.path.getsize(OUT) / 1024 / 1024
    print(f"saved {OUT} ({size:.1f} MB), {TOTAL} frames @ {FPS}fps = {DUR:.0f}s")

if __name__ == "__main__":
    main()

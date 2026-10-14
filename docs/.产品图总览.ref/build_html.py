# -*- coding: utf-8 -*-
"""产品图总览.html 生成器：与 build.py 同一套 MAPPING，数据驱动，可重复执行"""
import os, sys, html, json

BASE = r"D:/WorkbuddyTemp/2026-10-10-21-21-06/McMuseum"
PDIR = os.path.join(BASE, "web", "assets", "products")
OUT = os.path.join(BASE, "docs", "产品图总览.html")
sys.path.insert(0, os.path.join(BASE, "scripts"))
import revival

# 与 build.py 保持一致（手工同步）
MAPPING = {
    "shake_fries": ("shake_fries.png", "官方菜单图"),
    "purple_sweet_potato_pie": ("purple_sweet_potato_pie.gif", "官方菜单图"),
    "taro_pie": ("taro_pie.gif", "官方菜单图"),
    "big_chicken_steak": ("big_chicken_steak.png", "官方菜单图"),
    "apple_pie": ("apple_pie.gif", "官方菜单图"),
    "shake_fries_fun": ("shake_fries_fun.png", "官方菜单图"),
    "peach_pie": ("peach_pie.gif", "官方菜单图"),
    "mango_pie": ("mango_pie.gif", "官方菜单图"),
    "custard_pie": ("custard_pie.gif", "官方菜单图"),
    "braised_spicy_burger": ("braised_spicy_burger.png", "官方菜单图"),
    "grilled_chicken_burger": ("grilled_chicken_burger.png", "官方菜单图"),
    "kakazu_crispy_chicken": ("../v-crispy.png", "设计稿插画"),
    "matcha_mcfloat": ("../v-mcflurry.png", "设计稿插画"),
    "sakura_mcfloat": ("sakura_mcfloat.jpg", "官方海报·去水印抠图"),
    "garlic_chili_sauce": ("garlic_chili_sauce.jpg", "网络搜集·已白底化"),
    "mc_rice_wrap": ("mc_rice_wrap.jpg", "网络搜集·已白底化"),
    "angus_burger": ("angus_burger.jpg", "网络搜集·已白底化"),
    "cilantro_mcfloat": ("cilantro_mcfloat.png", "用户实拍/替换素材"),
    "youtiao_doujiang": ("youtiao_doujiang.jpg", "网络搜集·已白底化"),
    "treasure_triangle": ("treasure_triangle.png", "用户实拍/替换素材"),
    "strawberry_milkshake": ("strawberry_milkshake.jpg", "网络搜集·已白底化"),
    "milkshake": ("milkshake.jpg", "网络搜集·已白底化"),
    "veggie_cup": ("veggie_cup.jpg", "网络搜集·已白底化"),
    "mccool": ("mccool.jpg", "网络搜集·已白底化"),
    "vcut_wedges": ("vcut_wedges.jpg", "网络搜集·已白底化"),
    "curry_wing": ("curry_wing.jpg", "网络搜集·已白底化"),
    "maple_pancake_burger": ("maple_pancake_burger.jpg", "网络搜集·已白底化"),
}
if os.path.exists(os.path.join(BASE, "docs", ".产品图总览.ref", "mapping.json")):
    MAPPING.update(json.load(open(os.path.join(BASE, "docs", ".产品图总览.ref", "mapping.json"), encoding="utf-8")))

STATUS_ZH = {
    "limited_ended": "限定·已结束",
    "seasonal_return": "节令返场",
    "on_sale": "在售参照",
    "regional_on_sale": "区域在售参照",
    "needs_verification": "供应待核实",
}

prods = revival.get_products()
have, miss = [], []
for p in prods:
    pid = p["id"]
    m = MAPPING.get(pid)
    fname = m[0] if m else pid + ".jpg"
    src = m[1] if m else "待补图"
    img = os.path.join(PDIR, fname)
    if m and os.path.exists(img):
        have.append((p, fname, src))
    elif not m and any(os.path.exists(os.path.join(PDIR, pid + e)) for e in (".jpg", ".png", ".gif", ".jpeg", ".webp")):
        have.append((p, pid + ".jpg", src if src != "待补图" else "已接入"))
    else:
        miss.append((p, fname))

def row_miss(p, fname):
    return f'''        <tr class="miss">
          <td class="imgcell emoji">🥫</td>
          <td><b>{html.escape(p["name"])}</b><div class="pid">{p["id"]}</div></td>
          <td><span class="tag no">缺失 · 待补图</span><div class="src">建议文件名：{html.escape(fname)}</div></td>
        </tr>'''

def _have_row(p, fname, src):
    st = STATUS_ZH.get(p.get("status", ""), "")
    ev = p.get("evidence_level", "")
    extra = ((" · " + st) if st else "") + ((" · 证据" + str(ev)) if ev else "")
    return f'''        <tr>
          <td class="imgcell"><img src="web/assets/products/{html.escape(fname)}" alt="" loading="lazy"></td>
          <td><b>{html.escape(p["name"])}</b><div class="pid">{p["id"]}</div></td>
          <td><span class="tag ok">{html.escape(fname)}</span><div class="src">{html.escape(src + extra)}</div></td>
        </tr>'''

rows_h = "\n".join(_have_row(p, f, s) for p, f, s in have)
rows_m = "\n".join(row_miss(p, f) for p, f in miss)

page = f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>产品图总览 · 麦麦复活赛</title>
<style>
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:1100px;margin:0 auto;padding:20px;color:#3B2B20;background:#FFFDF7}}
h1{{font-size:24px;margin:0 0 6px}}
.sub{{
font-size:13px;color:#8A7F72}}
.summary{{margin:14px 0}}
.pill{{display:inline-block;padding:4px 12px;border-radius:999px;font-size:13px;margin-right:8px}}
.pill.a{{background:#E8F7EE;color:#1B7A3D}} .pill.b{{background:#FFF0F2;color:#C0392B}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
td,th{{border-bottom:1px solid #EFE6D8;padding:8px 6px;vertical-align:middle;text-align:left}}
.imgcell{{width:90px}} .imgcell img{{width:80px;height:80px;object-fit:contain;background:#fff;border:1px solid #F0E8DC;border-radius:8px}}
.imgcell.emoji{{font-size:34px;text-align:center;color:#C8BBA8}}
.pid{{font-size:12px;color:#B0A492;font-family:Consolas,monospace}}
.tag{{display:inline-block;font-size:12px;padding:2px 8px;border-radius:6px}}
.tag.ok{{background:#E8F7EE;color:#1B7A3D}} .tag.no{{background:#FFF0F2;color:#C0392B}}
.src{{font-size:12px;color:#8A7F72;margin-top:4px}}
h2{{font-size:18px;margin:26px 0 10px}}
tr.miss td{{color:#9A8D7B}}
</style></head><body>
<h1>产品图总览 · 麦麦复活赛</h1>
<div class="sub">共 {len(prods)} 款（投票池 {sum(1 for p in prods if p.get("vote_eligible"))} 款） · 图片文件位于 <code>web/assets/products/</code> · 替换同名文件后告诉我即可更新页面</div>
<div class="summary">
  <span class="pill a">✅ 有图 {len(have)} 款</span>
  <span class="pill b">❌ 缺失 {len(miss)} 款</span>
</div>
<h2>已接入图片（{len(have)}）</h2>
<table><tr><th>图片</th><th>产品名 / id</th><th>文件名 / 来源</th></tr>
{rows_h}
</table>
<h2>缺失待补（{len(miss)}）</h2>
<table><tr><th>占位</th><th>产品名 / id</th><th>建议</th></tr>
{rows_m}
</table>
</body></html>'''
open(OUT, "w", encoding="utf-8").write(page)
print(f"saved {OUT} | {len(prods)} products, {len(have)} with image, {len(miss)} missing")

# -*- coding: utf-8 -*-
"""第4条指令收尾：删除 twisty_fries + 珍宝三角/香菜冰旋风换图。"""
import json, os, shutil, sys
from PIL import Image

BASE = r"D:/WorkbuddyTemp/2026-10-10-21-21-06/McMuseum"
PROD_JSON = os.path.join(BASE, "data", "nostalgic_products.json")
ISSUE_MAP = os.path.join(BASE, "data", "issue_map.json")
PDIR = os.path.join(BASE, "web", "assets", "products")
SRC_DIR = os.path.join(BASE, "docs", "替换产品图")

def compress_to(src, dst, max_side=900):
    im = Image.open(src).convert("RGBA")
    im.thumbnail((max_side, max_side), Image.LANCZOS)
    # 合成白底再存 PNG，避免透明边
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.paste(im, mask=im.split()[3] if im.mode == "RGBA" else None)
    bg.convert("RGB").save(dst, "PNG", optimize=True)
    return os.path.getsize(dst)

# ---- 1. 产品 JSON：删 twisty_fries + 换图 ----
data = json.load(open(PROD_JSON, encoding="utf-8"))
prods = data["products"]
new_prods = [p for p in prods if p["id"] != "twisty_fries"]
assert len(prods) - len(new_prods) == 1, f"删除计数异常 {len(prods)}->{len(new_prods)}"

IMG_FIELDS = {
    "image_status": "unverified",
    "image_source_url": "",
    "image_source_name": "未知",
    "image_rights": "用户 2026-10-14 直接提供（docs/替换产品图/），原始出处与授权待补录",
    "image_confidence": "medium",
    "image_note": "",
}
SWAP = {
    "treasure_triangle": ("珍宝三角.png", "assets/products/treasure_triangle.png"),
    "cilantro_mcfloat": ("香菜冰旋风.png", "assets/products/cilantro_mcfloat.png"),
}
for p in new_prods:
    if p["id"] in SWAP:
        fname_src, rel = SWAP[p["id"]]
        src = os.path.join(SRC_DIR, fname_src)
        dst = os.path.join(BASE, "web", rel)
        size = compress_to(src, dst)
        p["image"] = rel
        p.update(IMG_FIELDS)
        print(f"换图 {p['id']}: {fname_src} -> {rel} ({size//1024}KB)")

data["products"] = new_prods
data["updated"] = "2026-10-14"
json.dump(data, open(PROD_JSON, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"产品 JSON: {len(prods)} -> {len(new_prods)}（删 twisty_fries）")

# ---- 2. issue_map：移除 twisty_fries ----
imap = json.load(open(ISSUE_MAP, encoding="utf-8"))
if "twisty_fries" in imap:
    del imap["twisty_fries"]
    json.dump(imap, open(ISSUE_MAP, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("issue_map: 移除 twisty_fries")
else:
    print("issue_map: 无 twisty_fries（已无残留）")

# ---- 3. 删除 twisty_fries 旧资产 ----
old_asset = os.path.join(PDIR, "twisty_fries.png")
if os.path.exists(old_asset):
    os.remove(old_asset)
    print(f"删除旧资产 {old_asset}")
else:
    print("旧资产 twisty_fries.png 不存在")

# ---- 4. 统计 eligible ----
elig = sum(1 for p in new_prods if p.get("vote_eligible"))
print(f"vote_eligible=True 计数: {elig} / 总数 {len(new_prods)}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 39 款无官方图的怀旧单品搜集真实网络图片（必应图片搜索）。"""
import json, os, re, sys, time, html, urllib.request, urllib.parse

sys.path.insert(0, "scripts")
import revival

OUT = "web/assets/products"
os.makedirs(OUT, exist_ok=True)

# 已有图的单品（官方 12 + 设计稿 3）
HAVE = {
    "shake_fries", "purple_sweet_potato_pie", "taro_pie", "big_chicken_steak",
    "twisty_fries", "apple_pie", "shake_fries_fun", "peach_pie", "mango_pie",
    "custard_pie", "braised_spicy_burger", "grilled_chicken_burger",
    "kakazu_crispy_chicken", "matcha_mcfloat",
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

def bing_images(query, limit=8):
    url = "https://cn.bing.com/images/search?q=" + urllib.parse.quote(query) + "&form=HDRSC2&first=1"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        page = html.unescape(r.read().decode("utf-8", "ignore"))
    urls = re.findall(r'"murl":"(https?://[^"]+?)"', page)
    # 去重保序
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out

def download(url, dst_base, min_bytes=6000):
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    dst = dst_base + ext
    req = urllib.request.Request(url, headers={**UA, "Referer": "https://cn.bing.com/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    if len(data) < min_bytes:
        raise ValueError(f"文件过小 {len(data)}B")
    open(dst, "wb").write(data)
    return dst, len(data)

def verify(path):
    from PIL import Image
    im = Image.open(path)
    w, h = im.size
    return w >= 200 and h >= 150

def main():
    prods = revival.get_products()
    todo = [p for p in prods if p["id"] not in HAVE]
    print(f"待搜集 {len(todo)} 款")
    ok, fail = [], []
    for i, p in enumerate(todo, 1):
        pid, name = p["id"], p["name"]
        short = re.sub(r"（.*?）", "", name)
        queries = [f"麦当劳 {short} 实物", f"麦当劳 {name}", f"{short} 麦当劳"]
        done = False
        for q in queries:
            try:
                urls = bing_images(q)
            except Exception as e:
                print(f"[{i}/{len(todo)}] {name} 搜索失败 {q}: {str(e)[:40]}")
                continue
            for u in urls:
                try:
                    dst, size = download(u, os.path.join(OUT, pid))
                    if verify(dst):
                        ok.append({"id": pid, "name": name, "file": os.path.basename(dst), "src": u})
                        print(f"[{i}/{len(todo)}] ✅ {name} <- {u[:70]}")
                        done = True
                        break
                    else:
                        os.remove(dst)
                except Exception:
                    continue
            if done:
                break
            time.sleep(0.4)
        if not done:
            fail.append({"id": pid, "name": name})
            print(f"[{i}/{len(todo)}] ❌ {name} 未找到")
        time.sleep(0.6)
    json.dump({"ok": ok, "fail": fail}, open("data/_img_collect.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n成功 {len(ok)} / 失败 {len(fail)}")

if __name__ == "__main__":
    main()

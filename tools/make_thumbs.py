import os, json
from PIL import Image

ROOT = r"C:\Users\Windows\Desktop\work\projects\nonone\whale-girl\docs"
THUMB = os.path.join(ROOT, "thumbs")
os.makedirs(THUMB, exist_ok=True)

MAX_EDGE = 1600      # 长边上限
QUALITY  = 80
METHOD   = 6

groups = ["sheets", "moegirl", "refs", "gallery", "wallpaper"]
manifest = []

for g in groups:
    d = os.path.join(ROOT, g)
    if not os.path.isdir(d):
        continue
    for fn in sorted(os.listdir(d)):
        src = os.path.join(d, fn)
        if not os.path.isfile(src):
            continue
        if not fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        base = os.path.splitext(fn)[0]
        out = os.path.join(THUMB, base + ".webp")
        rel_src = f"{g}/{fn}"
        rel_out = f"thumbs/{base}.webp"

        before = os.path.getsize(src)
        with Image.open(src) as im:
            im = im.convert("RGB") if im.mode in ("P", "LA", "RGBA") and g not in ("refs",) else im
            if im.mode in ("P", "LA"):
                im = im.convert("RGBA")
            w, h = im.size
            scale = min(1.0, MAX_EDGE / max(w, h))
            if scale < 1.0:
                im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
            if im.mode == "RGBA":
                im.save(out, "WEBP", quality=QUALITY, method=METHOD)
            else:
                im.convert("RGB").save(out, "WEBP", quality=QUALITY, method=METHOD)
        after = os.path.getsize(out)
        manifest.append({"src": rel_src, "thumb": rel_out, "before": before, "after": after,
                         "orig": f"{w}x{h}"})

with open(os.path.join(ROOT, "thumbs", "_manifest.json"), "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=1)

total_before = sum(m["before"] for m in manifest)
total_after = sum(m["after"] for m in manifest)
print(f"images: {len(manifest)}")
print(f"before: {total_before/1024/1024:.2f} MB")
print(f"after : {total_after/1024/1024:.2f} MB")
print(f"ratio : {total_before/total_after:.1f}x")
print("-" * 64)
for m in sorted(manifest, key=lambda x: -x["before"])[:12]:
    print(f"  {m['src']:<42} {m['before']/1024:8.1f} KB -> {m['after']/1024:7.1f} KB  ({m['orig']})")
